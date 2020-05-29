import logging
import time
from arnparse import arnparse

from spaceone.core.manager import BaseManager
from spaceone.monitoring.connector.aws_boto_connector import AWSBotoConnector
from spaceone.monitoring.error import *

_LOGGER = logging.getLogger(__name__)

_CLOUDWATCH_ARN_MAP = {
    'ec2/instance': {
        'namespace': 'AWS/EC2',
        'dimension_key': 'InstanceId'
    },
    'ec2/volume': {
        'namespace': 'AWS/EBS',
        'dimension_key': 'VolumeId'
    }
}

_STAT_MAP = {
    'AVERAGE': 'Average',
    'MAX': 'Maximum',
    'MIN': 'Minimum',
    'SUM': 'Sum'
}


class AWSManager(BaseManager):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aws_connector: AWSBotoConnector = self.locator.get_connector('AWSBotoConnector')

    def verify(self, options, secret_data):
        self.aws_connector.create_session(options, secret_data)

    def list_metrics(self, options, secret_data, resource):
        arn = self._parse_arn(resource)
        secret_data['region_name'] = arn.region

        namespace, dimensions = self._get_cloudwatch_query(arn, resource)

        self.aws_connector.create_session(options, secret_data)
        return self.aws_connector.list_metrics(namespace, dimensions)

    def get_metric_data(self, options, secret_data, resource, metric, start, end, period, stat):
        arn = self._parse_arn(resource)
        secret_data['region_name'] = arn.region

        namespace, dimensions = self._get_cloudwatch_query(arn, resource)

        if period is None:
            period = self._make_period_from_time_range(start, end)

        stat = self._convert_stat(stat)

        self.aws_connector.create_session(options, secret_data)
        return self.aws_connector.get_metric_data(namespace, dimensions, metric, start, end, period, stat)

    @staticmethod
    def _convert_stat(stat):
        if stat is None:
            stat = 'AVERAGE'

        if stat not in _STAT_MAP.keys():
            raise ERROR_NOT_SUPPORT_STAT(supported_stat=' | '.join(_STAT_MAP.keys()))

        return _STAT_MAP[stat]

    @staticmethod
    def _make_period_from_time_range(start, end):
        start_time = int(time.mktime(start.timetuple()))
        end_time = int(time.mktime(end.timetuple()))
        time_delta = end_time - start_time

        # Max 60 point in start and end time range
        if time_delta <= 60*60:         # ~ 1h
            return 60
        elif time_delta <= 60*60*6:     # 1h ~ 6h
            return 60*10
        elif time_delta <= 60*60*12:    # 6h ~ 12h
            return 60*20
        elif time_delta <= 60*60*24:    # 12h ~ 24h
            return 60*30
        elif time_delta <= 60*60*24*3:  # 1d ~ 2d
            return 60*60
        elif time_delta <= 60*60*24*7:  # 3d ~ 7d
            return 60*60*3
        elif time_delta <= 60*60*24*14:  # 1w ~ 2w
            return 60*60*6
        elif time_delta <= 60*60*24*14:  # 2w ~ 4w
            return 60*60*12
        else:                            # 4w ~
            return 60*60*24

    @staticmethod
    def _parse_arn(resource):
        try:
            arn = arnparse(resource)
        except Exception as e:
            raise ERROR_INVALID_RESOURCE_FORMAT()

        return arn

    @staticmethod
    def _get_cloudwatch_query(arn, resource):
        service = arn.service
        resource_type = arn.resource_type or ''
        resource_key = f'{service}/{resource_type}'
        resource_value = arn.resource

        if resource_key not in _CLOUDWATCH_ARN_MAP:
            raise ERROR_NOT_SUPPORT_RESOURCE(resource=resource)

        if resource_value is None:
            raise ERROR_INVALID_RESOURCE_FORMAT()

        query_conf = _CLOUDWATCH_ARN_MAP[resource_key]

        namespace = query_conf['namespace']
        dimensions = [{
            'Name': query_conf['dimension_key'],
            'Value': resource_value
        }]

        return namespace, dimensions
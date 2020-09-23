from asgiref.sync import async_to_sync
from rest_framework.utils.encoders import JSONEncoder
from channels.layers import get_channel_layer
import json


channel_layer = get_channel_layer()


async def groupSend(group, stream, payload):
    
    await channel_layer.group_send(
        group,
        {
            'type': 'group.send_encoded',
            'content': json.dumps({
                'stream': stream,
                'payload': payload
            }, cls=JSONEncoder)
        }
    )


def groupSendSync(group, stream, payload):
    async_to_sync(groupSend)(
        group,
        stream,
        payload
    )
from rest_framework.utils.encoders import JSONEncoder
import json


class DRFJsonConsumerMixinAsync:
  
    @classmethod
    async def encode_json(cls, content):
        return json.dumps(content, cls=JSONEncoder)

    async def group_send_encoded(self, data):
        await self.send(text_data=data['content'])
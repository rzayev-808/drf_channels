from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf.urls import url
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.testing import WebsocketCommunicator
from channels.routing import URLRouter
from rest_framework import serializers
from asgiref.sync import sync_to_async
from drf_async.jsonasync import AzPUG
from channels_oneway.mixins import DRFJsonConsumerMixinAsync
import pytest

User = get_user_model()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_azpug():
    class TestAzPUG(AzPUG):
        model = User
        stream = 'users'
        m2m_senders = [User.groups.through]

        @classmethod
        def group_names(cls, instance):
            return ['test']

        def serialize_data(self, instance):
            return {'id': instance.id, 'username': instance.username}

    class TestConsumer(AsyncJsonWebsocketConsumer, DRFJsonConsumerMixinAsync):
        async def connect(self):
            await self.channel_layer.group_add('test', self.channel_name)
            await self.accept()

        async def disconnect(self, close_code):
            await self.channel_layer.group_discard('test', self.channel_name)

    application = URLRouter([
        url(r"^testws/$", TestConsumer),
    ])

    communicator = WebsocketCommunicator(application, "/testws/")
    connected, subprotocol = await communicator.connect()
    assert connected

    user = await sync_to_async(User.objects.create)(username='root')

    response = await communicator.receive_json_from()

    assert response == {
        'stream': 'users',
        'payload': {
            'action': 'create',
            'data': {'id': 1, 'username': 'root'},
            'model': 'auth.user',
            'pk': 1
        }
    }

    user.username = 'SuperUser'

    await sync_to_async(user.save)()

    response = await communicator.receive_json_from()

    assert response == {
        'stream': 'users',
        'payload': {
            'action': 'update',
            'data': {'id': 1, 'username': 'SuperUser'},
            'model': 'auth.user',
            'pk': 1
        }
    }

    group = await sync_to_async(Group.objects.create)(name='group')

    await sync_to_async(user.groups.set)([group])

    response = await communicator.receive_json_from()

    assert response == {
        'stream': 'users',
        'payload': {
            'action': 'update',
            'data': {'id': 1, 'username': 'SuperUser'},
            'model': 'auth.user',
            'pk': 1
        }
    }

    await sync_to_async(user.delete)()

    response = await communicator.receive_json_from()

    assert response == {
        'stream': 'users',
        'payload': {
            'action': 'delete',
            'data': {'id': 1, 'username': 'SuperUser'},
            'model': 'auth.user',
            'pk': 1
        }
    }

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_serializer_azpug():
    class UserSerializer(serializers.ModelSerializer):
        class Meta:
            model = User
            fields = ('id', 'username', 'first_name', 'last_name')

    class TestAzPUG(AzPUG):
        model = User
        stream = 'users'
        serializer = UserSerializer

        @classmethod
        def group_names(cls, instance):
            return ['users']

    class TestConsumer(AsyncJsonWebsocketConsumer, DRFJsonConsumerMixinAsync):
        async def connect(self):
            await self.channel_layer.group_add('users', self.channel_name)
            await self.accept()

        async def disconnect(self, close_code):
            await self.channel_layer.group_discard('users', self.channel_name)

    application = URLRouter([
        url(r"^testws/$", TestConsumer),
    ])

    communicator = WebsocketCommunicator(application, "/testws/")
    connected, subprotocol = await communicator.connect()
    assert connected

    await sync_to_async(User.objects.create)(username='root')

    response = await communicator.receive_json_from()

    assert response == {
        'stream': 'users',
        'payload': {
            'action': 'create',
            'data': {
                'id': 2,
                'username': 'root',
                'first_name': '',
                'last_name': ''
            },
            'model': 'auth.user',
            'pk': 2
        }
    }

    await communicator.disconnect()
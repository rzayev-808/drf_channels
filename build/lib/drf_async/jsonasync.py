from django.db.models.signals import (
    post_delete,
    post_save,
    pre_delete,
    pre_save,
    m2m_changed
)
from django.db import transaction
from .utils import groupSendSync

"""
This is heavly inspired from the bindings that existed in channels v1.
"""

CREATE = 'create'
UPDATE = 'update'
DELETE = 'delete'


class AzPUGMetaClass(type):
    def __new__(cls, clsname, bases, attrs, **kwargs):
        newclass = super().__new__(cls, clsname, bases, attrs, **kwargs)

        if newclass.model is not None:
            newclass.register()

        return newclass


class AzPUG(object, metaclass=AzPUGMetaClass):
   

    model = None
    stream = None
    serializer = None
    m2m_senders = []
    signal_kwargs = None

    @classmethod
    def register(cls):
       
        pre_save.connect(cls.pre_save_receiver, sender=cls.model)
        post_save.connect(cls.post_save_receiver, sender=cls.model)
        pre_delete.connect(cls.pre_delete_receiver, sender=cls.model)
        post_delete.connect(cls.post_delete_receiver, sender=cls.model)

        for sender in cls.m2m_senders:
            m2m_changed.connect(cls.m2m_changed_receiver, sender=sender)

        cls.model_label = f'{cls.model._meta.app_label.lower()}.{cls.model._meta.object_name.lower()}'


    @classmethod
    def m2m_changed_receiver(cls, instance, action, **kwargs):
        if action.startswith('pre_'):
            cls.pre_change_receiver(instance, UPDATE, **kwargs)
        else:
            cls.post_change_receiver(instance, UPDATE, **kwargs)

    @classmethod
    def pre_save_receiver(cls, instance, **kwargs):
        creating = instance._state.adding
        cls.pre_change_receiver(instance, CREATE if creating else UPDATE)

    @classmethod
    def post_save_receiver(cls, instance, created, **kwargs):
        transaction.on_commit(
            lambda: cls.post_change_receiver(
                instance,
                CREATE if created else UPDATE,
                **kwargs
            )
        )

    @classmethod
    def pre_delete_receiver(cls, instance, **kwargs):
        cls.pre_change_receiver(instance, DELETE)

    @classmethod
    def post_delete_receiver(cls, instance, **kwargs):
        cls.post_change_receiver(instance, DELETE, **kwargs)

    @classmethod
    def pre_change_receiver(cls, instance, action, **kwargs):
        
        if action == CREATE:
            group_names = set()
        else:
            group_names = set(cls.group_names(instance))

        if not hasattr(instance, '_azpug_group_names'):
            instance._azpug_group_names = {}
        instance._azpug_group_names[cls] = group_names

    @classmethod
    def post_change_receiver(cls, instance, action, **kwargs):
       
        old_group_names = instance._azpug_group_names[cls]
        if action == DELETE:
            new_group_names = set()
        else:
            new_group_names = set(cls.group_names(instance))

        self = cls()
        self.instance = instance

        self.send_messages(instance, old_group_names - new_group_names, DELETE, **kwargs)
        self.send_messages(instance, old_group_names & new_group_names, UPDATE, **kwargs)
        self.send_messages(instance, new_group_names - old_group_names, CREATE, **kwargs)

    def send_messages(self, instance, group_names, action, **kwargs):
        
        if not group_names:
            return 
        self.signal_kwargs = kwargs
        payload = self.serialize(instance, action)
        if payload == {}:
            return  

        assert self.stream is not None
        for group_name in group_names:
            groupSendSync(group_name, self.stream, payload)

    @classmethod
    def group_names(cls, instance):
       
        raise NotImplementedError()

    def serialize(self, instance, action):
        payload = {
            "action": action,
            "pk": instance.pk,
            "data": self.serialize_data(instance),
            "model": self.model_label,
        }
        return payload

    def serialize_data(self, instance):
        
        assert self.serializer is not None

        return self.serializer(instance).data
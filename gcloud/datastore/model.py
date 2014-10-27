from gcloud import datastore
from gcloud.datastore import entity, key
try:
  import json
except ImportError:
  import simplejson as json

import datetime

class Key(key.Key):
    def __init__(self, *args, **kwargs):
        app = kwargs.get("app")
        namespace = kwargs.get("namespace")
        pairs = kwargs.get("pairs")
        flat = kwargs.get("flat")
        urlsafe = kwargs.get("urlsafe")
        path = kwargs.get("path")

        if urlsafe:
            raise NotImplementedError()

        if not path:
            if not pairs:
                if not flat:
                    flat = args

                assert len(flat) % 2 == 0
                pairs = [(flat[i], flat[i+1]) for i in range(0, len(flat), 2)]

            path = []
            for kind, _id in pairs:
                if isinstance(_id, (int, long)):
                    path.append({'kind': kind, 'id': _id})
                elif isinstance(_id, basestring):
                    path.append({'kind': kind, 'name': _id})
                else:
                    raise SyntaxError("id should be either int or string")

        super(Key, self).__init__(path, namespace=namespace, dataset_id=app)



dataset = None

class Property(object):
    def __init__(self, name=None, indexed=True, repeated=False, required=False, default=None, choices=None, validator=None):
        self._name = name
        self._indexed = indexed
        self._repeated = repeated
        self._required = required
        self._default = default
        self._choices = choices
        self._validator = validator

    def __get__(self, instance, owner):
        return self.from_base_type(instance.get(self._name))

    def __set__(self, instance, value):
        value = self.validate(value)
        instance[self._name] = self.to_base_type(value)

    def __del__(self, instance):
        instance.pop(self._name, None)

    def _fix_up(self, cls, name):
        if self._name is None:
            self._name = name

    def validate(self, value):
        assert self._choices is None or value in self._choices
        assert not (self._required and not value is None)
        if value is None: return

        v = self._validate(value)
        if not self._validator is None:
            return self._validator(self, value)

        return value

    def _validate(self, value):
        return value

    def to_base_type(self, value):
        if value is None:
            return value
        return self._to_base_type(value)

    def _to_base_type(self, value):
        return value

    def from_base_type(self, value):
        if value is None:
            return value
        return self._from_base_type(value)

    def _from_base_type(self, value):
        return value

    def _prepare_for_put(self, entity):
        pass

    def from_db_value(self, value):
        return self._from_db_value(value)

    def _from_db_value(self, value):
        return value

class BooleanProperty(Property):
    def _validate(self, value):
        assert isinstance(value, bool)
        return value

class IntegerProperty(Property):
    def _validate(self, value):
        assert isinstance(value, (int, long))
        return int(value)

class FloatProperty(Property):
    def _validate(self, value):
        assert isinstance(value, (int, long, float))
        return float(value)

class BlobProperty(Property):
    def __init__(self, name=None, compressed=False, **kwargs):
        super(BlobProperty, self).__init__(name=name, **kwargs)
        self._compressed = compressed
        assert not (compressed and self._indexed), "BlobProperty %s cannot be compressed and indexed at the same time." % self._name

    def _validate(self, value):
        assert isinstance(value, str), value
        return value

    def _to_base_type(self, value):
        if self._compressed:
            return zlib.compress(value)

        return value

    def _from_base_type(self, value):
        if self._compressed:
            return zlib.decompress(value.z_val)

        return value

class TextProperty(BlobProperty):
    def __init__(self, name=None, indexed=False, **kwargs):
        super(TextProperty, self).__init__(name=name, indexed=indexed, **kwargs)

    def _validate(self, value):
        if isinstance(value, str):
            value = value.decode('utf-8')

        assert isinstance(value, unicode)
        return value

    def _to_base_type(self, value):
        if isinstance(value, str):
            return value.decode('utf-8')

        return value

    def _from_base_type(self, value):
        if isinstance(value, str):
            return unicode(value, 'utf-8')
        elif isinstance(value, unicode):
            return value

    def _from_db_value(self, value):
        if isinstance(value, str):
            return value.decode('utf-8')

        return value

class StringProperty(TextProperty):
    def __init__(self, name=None, indexed=True, **kwargs):
        super(StringProperty, self).__init__(name=name, indexed=indexed, **kwargs)


class PickleProperty(BlobProperty):
    def _to_base_type(self, value):
        return super(PickleProperty, self)._to_base_type(pickle.dumps(value, pickle.HIGHEST_PROTOCOL))

    def _from_base_type(self, value):
        return pickle.loads(super(PickleProperty, self)._from_base_type(value))

    def _validate(self, value):
        return value

class JsonProperty(BlobProperty):
    def __init__(self, name=None, schema=None, **kwargs):
        super(JsonProperty, self).__init__(name, **kwargs)
        self._schema = schema

    def _to_base_type(self, value):
        return super(JsonProperty, self)._to_base_type(json.dumps(value))

    def _from_base_type(self, value):
        return json.loads(super(JsonProperty, self)._from_base_type(value))

    def _validate(self, value):
        return value


class DateTimeProperty(Property):
    def __init__(self, name=None, auto_now_add=False, auto_now=False, **kwargs):
        assert not ((auto_now_add or auto_now) and kwargs.get("repeated", False))
        super(DateTimeProperty, self).__init__(name, **kwargs)
        self._auto_now_add = auto_now_add
        self._auto_now = auto_now

    def _validate(self, value):
        assert isinstance(value, datetime.datetime), value
        return value

    def _now(self):
        return datetime.datetime.utcnow()

    def _prepare_for_put(self, entity):
        v = getattr(entity, self._name)
        if v is None and self._auto_now_add:
            setattr(entity, self._name, self._now())

        if self._auto_now:
            setattr(entity, self._name, self._now())


class DateProperty(DateTimeProperty):
    def _validate(self, value):
        assert isinstance(value, datetime.date)
        return value

    def _to_base_type(self, value):
        return datetime.datetime(value.year, value.month, value.day)

    def _from_base_type(self, value):
        return value.date()

    def _now(self):
        return datetime.datetime.utcnow().date()

class TimeProperty(DateTimeProperty):
    def _validate(self, value):
        assert isinstance(value, datetime.time)
        return value

    def _to_base_type(self, value):
        return datetime.datetime(
            1970, 1, 1,
            value.hour, value.minute, value.second,
            value.microsecond
        )

    def _from_base_type(self, value):
        return value.time()


class MetaModel(type):
    def __init__(cls, name, bases, classdict):
        super(MetaModel, cls).__init__(name, bases, classdict)
        cls._fix_up_properties()


class Model(entity.Entity):
    __metaclass__ = MetaModel

    # name, prop dict
    _properties = None
    _kind_map = {}

    def __init__(self, id=None, **kwargs):
        super(Model, self).__init__(dataset, self.__class__.__name__)
        if id is not None:
            self._key = self._key.id(id)

        for name in kwargs:
            setattr(self, name, kwargs[name])

    @classmethod
    def _fix_up_properties(cls):
        cls._properties = {}

        for name in cls.__dict__:
            attr = cls.__dict__[name]
            if isinstance(attr, Property):
                attr._fix_up(cls, name)
                cls._properties[attr._name] = attr

        cls._kind_map[cls.__name__] = cls

    @classmethod
    def _lookup_model(cls, kind):
        return cls._kind_map[kind]

    def __repr__(self):
        if self.key():
            return "<%s%s %s>" % (
                self.__class__.__name__,
                self.key().path(),
                super(Model, self).__repr__()
            )
        else:
            return "<%s %s>" % (
                self.__class__.__name__,
                super(Model, self).__repr__()
            )

    @classmethod
    def from_entity(cls, entity):
        obj = cls()
        obj._key = entity.key()

        for name in cls._properties:
            value = entity.get(name)
            # string property from protobuf is str, but gcloud-python need unicode
            obj[name] = cls._properties[name].from_db_value(value)

        return obj

    @classmethod
    def get_by_id(cls, id):
        entity = dataset.get_entity(Key.from_path(cls.__name__, id))
        if entity:
            return cls.from_entity(entity)

    @classmethod
    def get_multi(cls, ids):
        entities = dataset.get_entities([Key.from_path(cls.__name__, id) for id in ids])
        results = []

        for entity in entities:
            if entity is None:
                results.append(None)
            else:
                results.append(cls.from_entity(entity))

        return results

    def put(self):
        for name, prop in self._properties.items():
            prop._prepare_for_put(self)

        return self.save()


def get_multi(keys):
    entities = dataset.get_entities(keys)

    results = []
    for entity in entities:
        if entity is None:
            results.append(None)

        kind = entity.key().kind()

        model = Model._lookup_model(kind)
        results.append(model.from_entity(entity))

    return results

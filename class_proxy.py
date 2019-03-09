IGNORE_WRAPPED_METHODS = frozenset(
    (
        "__new__",
        "__init__",
        "__getattr__",
        "__setattr__",
        "__delattr__",
        "__getattribute__",
    )
)


def proxy_of(wrapped_class):
    def _decorator(proxy_class):
        return wrap_with(wrapped_class, proxy_class)

    return _decorator


def instance(obj):
    return obj.__instance__


def wrap_with(wrapped_class, proxy_class, ignore_base_methods=IGNORE_WRAPPED_METHODS):
    instances = _instance_wrapper()

    common = _mro_common(wrapped_class, proxy_class)
    base_methods = _resolve_proxy_members(proxy_class, common)
    base_methods.update(ignore_base_methods)
    resolution = _resolve_wrapped_members(wrapped_class, base_methods)

    members = {}
    members.update(
        {
            name: _proxied_value(base, name, instances)
            for name, base in resolution.items()
        }
    )
    members.update(proxy_class.__dict__)

    proxy_init = _resolve_without_get(proxy_class, "__init__")

    @_overwrite_method(members)
    def __init__(self, inner, *args, **kwargs):
        if not isinstance(inner, wrapped_class):
            raise TypeError(
                "type {!r} cannot wrap object {!r} with type {!r}".format(
                    type(self), inner, type(inner)
                )
            )
        instances.set_instance(self, inner)
        proxy_init(self, *args, **kwargs)

    @_overwrite_method(members, name="__instance__")
    @property
    def _instance_property(self):
        return instances.get_instance(self)

    return type(
        "{}[{}]".format(proxy_class.__name__, wrapped_class.__name__),
        (proxy_class,),
        members,
    )


def _overwrite_method(members, name=None):
    def _decorator(func):
        fname = name
        if fname is None:
            fname = func.__name__

        members[fname] = func
        return func

    return _decorator


class _deleted(object):
    pass


class _proxied_value(object):
    def __init__(self, base, name, instances):
        self._base = base
        self._name = name
        self._instances = instances

    def __get__(self, instance, owner):
        state = self._instances.get_state(instance)
        if self._name in state:
            result = state[self._name]

        elif self._name in self._base.__dict__:
            result = self._base.__dict__[self._name]
            owner = self._base
            if instance is not None:
                instance = self._instances.get_instance(instance)

        else:
            assert 0, "unreachable code"

        if result is _deleted:
            raise AttributeError(
                "type object {!r} has no attribute {!r}".format(
                    owner.__name__, self._name
                )
            )

        if hasattr(result, "__get__"):
            result = result.__get__(instance, owner)

        return result

    def __set__(self, instance, value):
        state = self._instances.get_state(instance)
        state[self._name] = value

    def __delete__(self, instance):
        state = self._instances.get_state(instance)
        state[self._name] = _deleted


class _instance_wrapper(object):
    def __init__(self):
        self._wrapped_objects = {}
        self._states = {}

    def set_instance(self, proxy, instance):
        self._wrapped_objects[id(proxy)] = instance

    def get_instance(self, proxy):
        return self._wrapped_objects[id(proxy)]

    def del_instance(self, proxy):
        del self._wrapped_objects[id(proxy)]
        self._states.pop(id(proxy), None)

    def get_state(self, proxy):
        if id(proxy) not in self._states:
            self._states[id(proxy)] = {}

        return self._states[id(proxy)]


def _resolve_without_get(cls, name):
    for base in cls.__mro__:
        if name in base.__dict__:
            return base.__dict__[name]

    raise AttributeError(name)


def _mro_common(left, right):
    left_mro = list(left.__mro__)
    left_mro.reverse()

    right_mro = list(right.__mro__)
    right_mro.reverse()

    result = [
        left_base
        for left_base, right_base in zip(left_mro, right_mro)
        if left_base == right_base
    ]
    result.reverse()

    return result


def _resolve_proxy_members(proxy_class, common):
    base_methods = set()
    for base in reversed(proxy_class.__mro__):
        if base in common:
            continue

        for name in base.__dict__.keys():
            base_methods.add(name)
    return base_methods


def _resolve_wrapped_members(wrapped_class, base_methods):
    resolution = {}
    for base in reversed(wrapped_class.__mro__):
        for name in base.__dict__.keys():
            if name in base_methods:
                continue

            resolution[name] = base

    return resolution

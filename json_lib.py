import json
import math
import pathlib
from dataclasses import dataclass
from typing import cast, ClassVar, NoReturn, Protocol, Self, Iterable, TypeAlias, TypeVar

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonArray: TypeAlias = list["JsonValue"]
JsonValue: TypeAlias = JsonObject | JsonArray | JsonPrimitive

JsonValuePathPart: TypeAlias = str | int
JsonValuePath: TypeAlias = tuple[JsonValuePathPart, ...]

def default_json_primitive() -> JsonPrimitive:
    return None

def default_json_object() -> JsonObject:
    return {}

def default_json_array() -> JsonArray:
    return []

def default_json_value() -> JsonValue:
    return None

def default_json_value_path() -> JsonValuePath:
    return ()

def _validate_json_value_path_part(x: object) -> None:
    if isinstance(x, bool):
        raise TypeError("JsonValuePathPart must be str or int, not bool")

    if isinstance(x, int):
        if x < 0:
            raise ValueError(f"JsonValuePathPart integer must be >= 0, got {x}")

        return

    if isinstance(x, str):
        return

    raise TypeError(f"Invalid JsonValuePathPart: {type(x).__name__}")

def _validate_json_value_path(x: object) -> None:
    if not isinstance(x, tuple):
        raise TypeError(f"JsonValuePath must be tuple, got {type(x).__name__}")

    for part in x:
        _validate_json_value_path_part(part)

def append_json_value_path_part(path: JsonValuePath, part: JsonValuePathPart) -> JsonValuePath:
    _validate_json_value_path(path)
    _validate_json_value_path_part(part)
    return path + (part,)

class JsonValueContext(object):
    def __init__(self, path: JsonValuePath = default_json_value_path(), max_depth: int = 1000):
        super(JsonValueContext, self).__init__()

        _validate_json_value_path(path)

        if isinstance(max_depth, bool) or (not isinstance(max_depth, int)):
            raise TypeError(f"max_depth must be int, got {type(max_depth).__name__}")

        if max_depth < 0:
            raise ValueError(f"max_depth must be >= 0, got {max_depth}")

        self.__path: JsonValuePath = path
        self.__max_depth: int = max_depth

    def get_path(self) -> JsonValuePath:
        return self.__path

    def get_max_depth(self) -> int:
        return self.__max_depth

    def create_child(self, path_part: JsonValuePathPart) -> "JsonValueContext":
        return JsonValueContext(self.get_path() + (path_part,), self.get_max_depth())

def _normalize_json_value_context(ctx: JsonValueContext | None) -> JsonValueContext:
    if ctx is None:
        return JsonValueContext()

    if not isinstance(ctx, JsonValueContext):
        raise TypeError(f"Expected JsonValueContext | None, got {type(ctx).__name__}")

    return ctx

class JsonObjectConvertible(Protocol):
    def to_json_object(self) -> JsonObject:
        ...

    @classmethod
    def from_json_object(cls: type[Self], json_object: JsonObject, *, ctx: JsonValueContext | None = None) -> Self:
        ...

def _escape_json_pointer_part(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")

def _json_value_path_to_pointer(path: JsonValuePath) -> str:
    if not path:
        return ""

    parts: list[str] = []

    for part in path:
        if isinstance(part, int) and (not isinstance(part, bool)):
            if part < 0:
                raise ValueError(f"Negative array index in JsonValuePath: {part}")

            parts.append(str(part))
        elif isinstance(part, str):
            parts.append(_escape_json_pointer_part(part))
        else:
            raise TypeError(f"Invalid JsonValuePathPart: {type(part).__name__}")

    return "/" + "/".join(parts)

class JsonValueError(ValueError):
    def __init__(self, reason: str, path: JsonValuePath):
        super(JsonValueError, self).__init__(reason)

        self.__path: JsonValuePath = path

    def get_path(self) -> JsonValuePath:
        return self.__path

    def __str__(self) -> str:
        reason: str = str(self.args[0]) if self.args else self.__class__.__name__

        try:
            pointer: str = _json_value_path_to_pointer(self.__path)
            at: str = pointer if pointer else "<root>"
        except Exception as e:
            try:
                path_repr = repr(self.__path)
            except Exception:
                path_repr = "<unreprable path>"

            at = f"<invalid path ({type(e).__name__}: {e}); path={path_repr}>"

        return f"{reason} at {at}"

def validate_json_primitive(x: object, *, ctx: JsonValueContext | None = None) -> None:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    if x is None:
        return

    if isinstance(x, bool):
        return

    if isinstance(x, str):
        return

    if isinstance(x, int):
        return

    if isinstance(x, float):
        if math.isfinite(x):
            return

        raise JsonValueError(f"Non-finite float: {x!r}", ctx.get_path())

    raise JsonValueError(f"Invalid primitive: {type(x).__name__} value={x!r}", ctx.get_path())

@dataclass(frozen=True, slots=True)
class _StackItem:
    discard: bool
    oid: int
    value: object
    depth: int
    path: JsonValuePath

    DUMMY_OID: ClassVar[int] = -1
    DUMMY_VALUE: ClassVar[object] = object()

def validate_json_value(x: object, *, ctx: JsonValueContext | None = None) -> None:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    active_oids: set[int] = set()
    stack: list[_StackItem] = [_StackItem(False, _StackItem.DUMMY_OID, x, 0, ctx.get_path())]

    while stack:
        item: _StackItem = stack.pop()

        if item.discard:
            active_oids.discard(item.oid)
            continue

        if item.depth > ctx.get_max_depth():
            raise JsonValueError(f"Max depth exceeded (depth={item.depth} > {ctx.get_max_depth()})", item.path)

        if isinstance(item.value, dict):
            value: JsonObject = cast(JsonObject, item.value)

            oid = id(value)

            if oid in active_oids:
                raise JsonValueError("Cycle detected (object)", item.path)

            active_oids.add(oid)
            stack.append(_StackItem(True, oid, _StackItem.DUMMY_VALUE, item.depth, item.path))

            items: list[tuple[object, object]] = list(value.items())

            for k, v in reversed(items):
                if not isinstance(k, str):
                    raise JsonValueError(f"Non-string object key: {k!r} (type={type(k).__name__})", item.path)

                child_path: JsonValuePath = append_json_value_path_part(item.path, k)
                stack.append(_StackItem(False, _StackItem.DUMMY_OID, v, item.depth + 1, child_path))
        elif isinstance(item.value, list):
            value: JsonArray = cast(JsonArray, item.value)

            oid = id(value)

            if oid in active_oids:
                raise JsonValueError("Cycle detected (array)", item.path)

            active_oids.add(oid)
            stack.append(_StackItem(True, oid, _StackItem.DUMMY_VALUE, item.depth, item.path))

            for i in range(len(value) - 1, -1, -1):
                child_path: JsonValuePath = append_json_value_path_part(item.path, i)
                stack.append(_StackItem(False, _StackItem.DUMMY_OID, value[i], item.depth + 1, child_path))
        else:
            validate_json_primitive(item.value, ctx=JsonValueContext(item.path, ctx.get_max_depth()))

def validate_json_object(x: object, *, ctx: JsonValueContext | None = None) -> None:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    if not isinstance(x, dict):
        raise JsonValueError(f"Expected JSON object, got {type(x).__name__}", ctx.get_path())

    validate_json_value(x, ctx=ctx)

def validate_json_array(x: object, *, ctx: JsonValueContext | None = None) -> None:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    if not isinstance(x, list):
        raise JsonValueError(f"Expected JSON array, got {type(x).__name__}", ctx.get_path())

    validate_json_value(x, ctx=ctx)

def dump_convertible(convertible: JsonObjectConvertible, path: pathlib.Path, *, ctx: JsonValueContext | None = None) -> None:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    o: JsonObject = convertible.to_json_object()

    try:
        validate_json_object(o, ctx=ctx)
    except JsonValueError as e:
        raise TypeError(f"Invalid JSON produced by {type(convertible).__name__} when writing {path}: {e}") from e

    s: str = json.dumps(o, ensure_ascii=False, allow_nan=False, indent=4, sort_keys=True)
    path.write_text(s, encoding="utf-8")

def _parse_float(s: str) -> float:
    f: float = float(s)

    if not math.isfinite(f):
        raise ValueError(f"Non-finite float: {s}")

    return f

def _parse_constant(s: str) -> NoReturn:
    raise ValueError(f"Invalid JSON constant: {s}")

T = TypeVar("T", bound=JsonObjectConvertible)
def load_convertible(cls: type[T], path: pathlib.Path, *, ctx: JsonValueContext | None = None) -> T:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    s: str = path.read_text(encoding="utf-8")

    try:
        o = json.loads(s, parse_float=_parse_float, parse_constant=_parse_constant)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse JSON in {path}: {e}") from e

    try:
        validate_json_object(o, ctx=ctx)
    except JsonValueError as e:
        raise TypeError(f"Invalid JSON in {path}: {e}") from e

    try:
        return cls.from_json_object(cast(JsonObject, o), ctx=ctx)
    except (JsonValueError, TypeError, ValueError) as e:
        raise TypeError(f"Failed to deserialize {cls.__name__} from {path}: {e}") from e

def get_str_from_json_object(obj: JsonObject, key: str, *, default: str = "") -> str:
    if key not in obj:
        return default

    value: object | None = obj[key]

    if not isinstance(value, str):
        return default

    return cast(str, value)

def get_int_from_json_object(obj: JsonObject, key: str, *, default: int = 0) -> int:
    if key not in obj:
        return default

    value: object | None = obj[key]

    if isinstance(value, bool)\
        or (not isinstance(value, int)):
        return default

    return cast(int, value)

def get_float_from_json_object(obj: JsonObject, key: str, *, default: float = 0.0) -> float:
    if key not in obj:
        return default

    value: object | None = obj[key]

    if isinstance(value, bool):
        return default

    if isinstance(value, int):
        try:
            return float(value)
        except OverflowError:
            return default

    if isinstance(value, float):
        if math.isfinite(value):
            return cast(float, value)
        else:
            return default

    return default

def get_bool_from_json_object(obj: JsonObject, key: str, *, default: bool = False) -> bool:
    if key not in obj:
        return default

    value: object | None = obj[key]

    if not isinstance(value, bool):
        return default

    return cast(bool, value)

def get_primitive_from_json_object(obj: JsonObject, key: str, *, default: JsonPrimitive = default_json_primitive(), ctx: JsonValueContext | None = None) -> JsonPrimitive:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    if key not in obj:
        return default

    value: object | None = obj[key]

    try:
        validate_json_primitive(value, ctx=child_ctx)
    except JsonValueError:
        return default

    return cast(JsonPrimitive, value)

def get_value_from_json_object(obj: JsonObject, key: str, *, default: JsonValue = default_json_value(), ctx: JsonValueContext | None = None) -> JsonValue:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    if key not in obj:
        return default

    value: object | None = obj[key]

    try:
        validate_json_value(value, ctx=child_ctx)
    except JsonValueError:
        return default

    return cast(JsonValue, value)

T_co = TypeVar("T_co", covariant=True)
class Factory(Protocol[T_co]):
    def __call__(self) -> T_co:
        ...

def get_object_from_json_object(obj: JsonObject, key: str, *, default_factory: Factory[JsonObject] = dict, ctx: JsonValueContext | None = None) -> JsonObject:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    if key not in obj:
        return default_factory()

    value: object | None = obj[key]

    try:
        validate_json_object(value, ctx=child_ctx)
    except JsonValueError:
        return default_factory()

    return cast(JsonObject, value)

def get_array_from_json_object(obj: JsonObject, key: str, *, default_factory: Factory[JsonArray] = list, ctx: JsonValueContext | None = None) -> JsonArray:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    if key not in obj:
        return default_factory()

    value: object | None = obj[key]

    try:
        validate_json_array(value, ctx=child_ctx)
    except JsonValueError:
        return default_factory()

    return cast(JsonArray, value)

T = TypeVar("T", bound=JsonObjectConvertible)
def get_convertible_from_json_object(obj: JsonObject, key: str, cls: type[T], default_factory: Factory[T], *, ctx: JsonValueContext | None = None) -> T:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    if key not in obj:
        return default_factory()

    value: object | None = obj[key]

    try:
        validate_json_object(value, ctx=child_ctx)
        return cls.from_json_object(cast(JsonObject, value), ctx=child_ctx)
    except (JsonValueError, TypeError, ValueError):
        return default_factory()

T = TypeVar("T", bound=JsonObjectConvertible)
def get_convertibles_from_json_object(obj: JsonObject, key: str, cls: type[T], *, default_factory: Factory[list[T]] = list, ctx: JsonValueContext | None = None) -> list[T]:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    if key not in obj:
        return default_factory()

    value: object | None = obj[key]

    array_ctx: JsonValueContext = ctx.create_child(key)

    try:
        validate_json_array(value, ctx=array_ctx)

        convertibles: list[T] = []

        for i, item in enumerate(cast(JsonArray, value)):
            item_ctx: JsonValueContext = array_ctx.create_child(i)
            validate_json_object(item, ctx=item_ctx)
            convertibles.append(cls.from_json_object(cast(JsonObject, item), ctx=item_ctx))

        return convertibles
    except (JsonValueError, TypeError, ValueError):
        return default_factory()

def _require_value_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> object | None:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    if key not in obj:
        raise JsonValueError("Missing required key", child_ctx.get_path())

    return obj[key]

def require_str_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> str:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)

    if not isinstance(value, str):
        raise JsonValueError(f"Expected string, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_int_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> int:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)

    if isinstance(value, bool) or (not isinstance(value, int)):
        raise JsonValueError(f"Expected integer, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_float_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> float:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)

    if isinstance(value, bool):
        raise JsonValueError("Expected number, got bool", child_ctx.get_path())

    if isinstance(value, int):
        try:
            return float(value)
        except OverflowError:
            raise JsonValueError(f"Integer too large to convert to float: {value!r}", child_ctx.get_path())

    if isinstance(value, float):
        if math.isfinite(value):
            return cast(float, value)
        else:
            raise JsonValueError(f"Non-finite float: {value!r}", child_ctx.get_path())

    raise JsonValueError(f"Expected number, got {type(value).__name__}", child_ctx.get_path())

def require_bool_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> bool:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)

    if not isinstance(value, bool):
        raise JsonValueError(f"Expected boolean, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_primitive_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> JsonPrimitive:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_primitive(value, ctx=child_ctx)
    return cast(JsonPrimitive, value)

def require_value_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> JsonValue:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_value(value, ctx=child_ctx)
    return value

def require_object_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> JsonObject:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_object(value, ctx=child_ctx)
    return cast(JsonObject, value)

def require_array_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> JsonArray:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_array(value, ctx=child_ctx)
    return cast(JsonArray, value)

T = TypeVar("T", bound=JsonObjectConvertible)
def require_convertible_from_json_object(obj: JsonObject, key: str, cls: type[T], *, ctx: JsonValueContext | None = None) -> T:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_object(value, ctx=child_ctx)
    return cls.from_json_object(cast(JsonObject, value), ctx=child_ctx)

T = TypeVar("T", bound=JsonObjectConvertible)
def require_convertibles_from_json_object(obj: JsonObject, key: str, cls: type[T], *, ctx: JsonValueContext | None = None) -> list[T]:
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)

    array_ctx: JsonValueContext = ctx.create_child(key)
    validate_json_array(value, ctx=array_ctx)

    convertibles: list[T] = []

    for i, item in enumerate(cast(JsonArray, value)):
        item_ctx: JsonValueContext = array_ctx.create_child(i)
        validate_json_object(item, ctx=item_ctx)
        convertibles.append(cls.from_json_object(cast(JsonObject, item), ctx=item_ctx))

    return convertibles

def convert_convertibles_to_json_objects(convertibles: Iterable[JsonObjectConvertible]) -> list[JsonObject]:
    json_objects: list[JsonObject] = []

    for i, convertible in enumerate(convertibles):
        json_object: JsonObject = convertible.to_json_object()

        try:
            validate_json_object(json_object, ctx=JsonValueContext((i,)))
        except JsonValueError as e:
            raise TypeError(f"Invalid JSON produced by element {i} ({type(convertible).__name__}): {e}") from e

        json_objects.append(json_object)

    return json_objects

__all__ = [
    "JsonPrimitive",
    "JsonObject",
    "JsonArray",
    "JsonValue",
    "JsonValuePathPart",
    "JsonValuePath",
    "default_json_primitive",
    "default_json_object",
    "default_json_array",
    "default_json_value",
    "default_json_value_path",
    "JsonValueError",
    "validate_json_primitive",
    "validate_json_value",
    "validate_json_object",
    "validate_json_array",
    "JsonObjectConvertible",
    "dump_convertible",
    "load_convertible",
    "get_str_from_json_object",
    "get_int_from_json_object",
    "get_float_from_json_object",
    "get_bool_from_json_object",
    "get_primitive_from_json_object",
    "get_value_from_json_object",
    "Factory",
    "get_object_from_json_object",
    "get_array_from_json_object",
    "get_convertible_from_json_object",
    "get_convertibles_from_json_object",
    "require_str_from_json_object",
    "require_int_from_json_object",
    "require_float_from_json_object",
    "require_bool_from_json_object",
    "require_primitive_from_json_object",
    "require_value_from_json_object",
    "require_object_from_json_object",
    "require_array_from_json_object",
    "require_convertible_from_json_object",
    "require_convertibles_from_json_object",
    "convert_convertibles_to_json_objects",
    "append_json_value_path_part",
    "JsonValueContext",
]

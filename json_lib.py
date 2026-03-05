import json
import math
import pathlib
from dataclasses import dataclass
from typing import cast, ClassVar, NoReturn, Protocol, Self, TypeAlias, TypeVar

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonObject: TypeAlias = dict[str, "JsonValue"]
JsonArray: TypeAlias = list["JsonValue"]
JsonValue: TypeAlias = JsonObject | JsonArray | JsonPrimitive

JsonValuePathToken: TypeAlias = str | int
JsonValuePath: TypeAlias = tuple[JsonValuePathToken, ...]

def escape_json_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")

def json_value_path_to_pointer(path: JsonValuePath) -> str:
    if not path:
        return ""

    tokens: list[str] = []

    for token in path:
        if isinstance(token, int) and (not isinstance(token, bool)):
            if token < 0:
                raise ValueError(f"Negative array index in JsonValuePath: {token}")

            tokens.append(str(token))
        elif isinstance(token, str):
            tokens.append(escape_json_pointer_token(token))
        else:
            raise TypeError(f"Invalid JsonValuePathToken: {type(token).__name__}")

    return "/" + "/".join(tokens)

class JsonValueError(ValueError):
    def __init__(self, reason: str, path: JsonValuePath):
        super().__init__(reason)
        self.path: JsonValuePath = path

    def __str__(self) -> str:
        pointer: str = json_value_path_to_pointer(self.path)
        at: str = pointer if pointer else "<root>"
        return f"{self.args[0]} at {at}"

def validate_json_primitive(x: object, *, path: JsonValuePath = ()) -> None:
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

        raise JsonValueError("Non-finite float", path)

    raise JsonValueError(f"Invalid primitive: {type(x).__name__}", path)

@dataclass(frozen=True, slots=True)
class StackItem:
    discard: bool
    oid: int
    value: object
    depth: int
    path: JsonValuePath

    DUMMY_OID: ClassVar[int] = -1
    DUMMY_VALUE: ClassVar[object] = object()

def validate_json_value(x: object, *, max_depth: int = 1000) -> None:
    active_oids: set[int] = set()
    stack: list[StackItem] = [StackItem(False, StackItem.DUMMY_OID, x, 0, ())]

    while stack:
        item: StackItem = stack.pop()

        if item.discard:
            active_oids.discard(item.oid)
            continue

        if item.depth > max_depth:
            raise JsonValueError(f"Max depth exceeded (>{max_depth})", item.path)

        if isinstance(item.value, dict):
            value: JsonObject = cast(JsonObject, item.value)

            oid = id(value)

            if oid in active_oids:
                raise JsonValueError("Cycle detected (object)", item.path)

            active_oids.add(oid)
            stack.append(StackItem(True, oid, StackItem.DUMMY_VALUE, item.depth, item.path))

            for k, v in value.items():
                if not isinstance(k, str):
                    raise JsonValueError("Non-string object key", item.path)

                stack.append(StackItem(False, StackItem.DUMMY_OID, v, item.depth + 1, item.path + (k,)))
        elif isinstance(item.value, list):
            value: JsonArray = cast(JsonArray, item.value)

            oid = id(value)

            if oid in active_oids:
                raise JsonValueError("Cycle detected (array)", item.path)

            active_oids.add(oid)
            stack.append(StackItem(True, oid, StackItem.DUMMY_VALUE, item.depth, item.path))

            for i, j in enumerate(value):
                stack.append(StackItem(False, StackItem.DUMMY_OID, j, item.depth + 1, item.path + (i,)))
        else:
            validate_json_primitive(item.value, path=item.path)

def validate_json_object(x: object, *, max_depth: int = 1000) -> None:
    if not isinstance(x, dict):
        raise JsonValueError(f"Expected JSON object, got {type(x).__name__}", ())

    validate_json_value(x, max_depth=max_depth)


def validate_json_array(x: object, *, max_depth: int = 1000) -> None:
    if not isinstance(x, list):
        raise JsonValueError(f"Expected JSON array, got {type(x).__name__}", ())

    validate_json_value(x, max_depth=max_depth)

class JsonObjectConvertible(Protocol):
    def to_json_object(self) -> JsonObject:
        ...

    @classmethod
    def from_json_object(cls: type[Self], json_object: JsonObject) -> Self:
        ...

def dump_json_object_convertible(convertible: JsonObjectConvertible, path: pathlib.Path) -> None:
    o: JsonObject = convertible.to_json_object()

    try:
        validate_json_object(o)
    except JsonValueError as e:
        raise TypeError(f"Invalid JSON produced by {type(convertible).__name__} for {path}: {e}") from e

    s: str = json.dumps(o, ensure_ascii=False, allow_nan=False, indent=4, sort_keys=True)
    path.write_text(s, encoding="utf-8")

def parse_float(s: str) -> float:
    f: float = float(s)

    if not math.isfinite(f):
        raise ValueError(f"Non-finite float: {s}")

    return f

def parse_constant(s: str) -> NoReturn:
    raise ValueError(f"Invalid JSON constant: {s}")

T = TypeVar("T", bound=JsonObjectConvertible)
def load_json_object_convertible(cls: type[T], path: pathlib.Path) -> T:
    s: str = path.read_text(encoding="utf-8")

    try:
        o = json.loads(s, parse_float=parse_float, parse_constant=parse_constant)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse JSON in {path}: {e}") from e

    try:
        validate_json_object(o)
    except JsonValueError as e:
        raise TypeError(f"Invalid JSON in {path}: {e}") from e

    return cls.from_json_object(cast(JsonObject, o))

def get_str_from_json_object(obj: JsonObject, key: str, *, default: str = "") -> str:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, str):
        return default

    return value

def get_int_from_json_object(obj: JsonObject, key: str, *, default: int = 0) -> int:
    value: JsonValue | None = obj.get(key)

    if isinstance(value, bool):
        return default

    if not isinstance(value, int):
        return default

    return value

def get_float_from_json_object(obj: JsonObject, key: str, *, default: float = 0.0) -> float:
    value: JsonValue | None = obj.get(key)

    if isinstance(value, bool):
        return default

    if isinstance(value, int):
        try:
            return float(value)
        except OverflowError:
            return default

    if not isinstance(value, float):
        return default

    if not math.isfinite(value):
        return default

    return value

def get_bool_from_json_object(obj: JsonObject, key: str, *, default: bool = False) -> bool:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, bool):
        return default

    return value

T_co = TypeVar("T_co", covariant=True)
class Factory(Protocol[T_co]):
    def __call__(self) -> T_co:
        ...

def get_object_from_json_object(obj: JsonObject, key: str, *, default_factory: Factory[JsonObject] = dict) -> JsonObject:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, dict):
        return default_factory()

    return cast(JsonObject, value)

def get_array_from_json_object(obj: JsonObject, key: str, *, default_factory: Factory[JsonArray] = list) -> JsonArray:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, list):
        return default_factory()

    return cast(JsonArray, value)

T = TypeVar("T", bound=JsonObjectConvertible)
def get_convertible_from_json_object(obj: JsonObject, key: str, cls: type[T], *, default_factory: Factory[T] | None = None) -> T:
    value: JsonValue | None = obj.get(key)

    if isinstance(value, dict):
        return cls.from_json_object(cast(JsonObject, value))

    if default_factory is not None:
        return default_factory()

    try:
        return cls()
    except TypeError as e:
        raise TypeError(f"{cls.__name__} must be constructible with no args, or pass default_factory") from e

T = TypeVar("T", bound=JsonObjectConvertible)
def get_convertibles_from_json_object(obj: JsonObject, key: str, cls: type[T], *, default_factory: Factory[list[T]] = list) -> list[T]:
    value: JsonValue | None = obj.get(key)

    if not isinstance(value, list):
        return default_factory()

    convertibles: list[T] = []

    for item in value:
        if isinstance(item, dict):
            convertibles.append(cls.from_json_object(cast(JsonObject, item)))
        else:
            return default_factory()

    return convertibles

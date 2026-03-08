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
    """Returns the default JSON primitive.

    Returns:
        The default JSON primitive, which is ``None``.
    """
    return None

def default_json_object() -> JsonObject:
    """Returns a new empty JSON object.

    Returns:
        A new empty JSON object.
    """
    return {}

def default_json_array() -> JsonArray:
    """Returns a new empty JSON array.

    Returns:
        A new empty JSON array.
    """
    return []

def default_json_value() -> JsonValue:
    """Returns the default JSON value.

    Returns:
        The default JSON value, which is ``None``.
    """
    return None

def default_json_value_path() -> JsonValuePath:
    """Returns the empty path for the JSON root.

    Returns:
        The empty path for the JSON root.
    """
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
    """Appends a part to a path.

    Args:
        path: Base path.
        part: Object key or array index to append.

    Returns:
        A new path with ``part`` appended.

    Raises:
        TypeError: Raised when ``path`` or ``part`` has an invalid type.
        ValueError: Raised when ``part`` is an invalid array index.
    """

    _validate_json_value_path(path)
    _validate_json_value_path_part(part)
    return path + (part,)

class JsonValueContext(object):
    """Stores a path and a maximum depth for JSON validation.

    Instances of this class carry the current path and the maximum allowed nesting depth so that validation and deserialization code can report precise paths inside nested structures.
    """

    def __init__(self, path: JsonValuePath = default_json_value_path(), max_depth: int = 1000):
        """Initializes a JSON value context.

        Args:
            path: Current path.
            max_depth: Maximum allowed nesting depth during validation.

        Raises:
            TypeError: Raised when ``path`` or ``max_depth`` has an invalid type.
            ValueError: Raised when ``max_depth`` is negative or when ``path`` contains an invalid part.
        """
        super(JsonValueContext, self).__init__()

        _validate_json_value_path(path)

        if isinstance(max_depth, bool) or (not isinstance(max_depth, int)):
            raise TypeError(f"max_depth must be int, got {type(max_depth).__name__}")

        if max_depth < 0:
            raise ValueError(f"max_depth must be >= 0, got {max_depth}")

        self.__path: JsonValuePath = path
        self.__max_depth: int = max_depth

    def get_path(self) -> JsonValuePath:
        """Returns the current path.

        Returns:
            The current path.
        """
        return self.__path

    def get_max_depth(self) -> int:
        """Returns the maximum validation depth.

        Returns:
            The maximum validation depth.
        """
        return self.__max_depth

    def create_child(self, path_part: JsonValuePathPart) -> "JsonValueContext":
        """Creates a child context for a nested path part.

        Args:
            path_part: Object key or array index to append to the current path.

        Returns:
            A new context for the child path.

        Raises:
            TypeError: Raised when ``path_part`` has an invalid type.
            ValueError: Raised when ``path_part`` is an invalid array index.
        """
        return JsonValueContext(self.get_path() + (path_part,), self.get_max_depth())

def _normalize_json_value_context(ctx: JsonValueContext | None) -> JsonValueContext:
    if ctx is None:
        return JsonValueContext()

    if not isinstance(ctx, JsonValueContext):
        raise TypeError(f"Expected JsonValueContext | None, got {type(ctx).__name__}")

    return ctx

class JsonObjectConvertible(Protocol):
    """Protocol for objects that can be converted to and from JSON objects."""
    def to_json_object(self) -> JsonObject:
        """Converts the convertible to a JSON object.

        Returns:
            The JSON object representation of the convertible.
        """
        ...

    @classmethod
    def from_json_object(cls: type[Self], json_object: JsonObject, *, ctx: JsonValueContext | None = None) -> Self:
        """Creates a convertible from a JSON object.

        Args:
            json_object: Source JSON object.
            ctx: Optional context for path-aware validation and error reporting.

        Returns:
            The deserialized convertible.
        """
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
    """Raised when a value is not a valid JSON value under this module's rules."""

    def __init__(self, reason: str, path: JsonValuePath):
        """Initializes the error with a reason and a path.

        Args:
            reason: Human-readable description of the failure.
            path: Path at which the failure occurred.
        """
        super(JsonValueError, self).__init__(reason)

        self.__path: JsonValuePath = path

    def get_path(self) -> JsonValuePath:
        """Returns the path associated with the error.

        Returns:
            The stored path.
        """
        return self.__path

    def __str__(self) -> str:
        """Formats the error with its path.

        Returns:
            A message that includes both the failure reason and a JSON Pointer-like path.
        """
        reason: str = str(self.args[0]) if self.args else self.__class__.__name__

        try:
            pointer: str = _json_value_path_to_pointer(self.__path)
            at: str = pointer if pointer else "<root>"
        except Exception as e:
            try:
                path_repr = repr(self.__path)
            except Exception:
                path_repr = "<unrepresentable path>"

            at = f"<invalid path ({type(e).__name__}: {e}); path={path_repr}>"

        return f"{reason} at {at}"

def validate_json_primitive(x: object, *, ctx: JsonValueContext | None = None) -> None:
    """Validates that a value is a JSON primitive.

    Accepted values are ``None``, ``bool``, ``str``, integers, and finite floating-point values.

    Args:
        x: Value to validate.
        ctx: Optional validation context.

    Returns:
        ``None``.

    Raises:
        JsonValueError: Raised when ``x`` is not a valid JSON primitive under this module's rules.
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Validates that a value is a JSON value.

    This validator traverses nested objects and arrays iteratively, enforces a maximum nesting depth, rejects non-string object keys, and detects cycles in container graphs.

    Args:
        x: Value to validate.
        ctx: Optional validation context.

    Returns:
        ``None``.

    Raises:
        JsonValueError: Raised when ``x`` is not a valid JSON value.
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Validates that a value is a JSON object.

    Args:
        x: Value to validate.
        ctx: Optional validation context.

    Returns:
        ``None``.

    Raises:
        JsonValueError: Raised when ``x`` is not a valid JSON object.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    if not isinstance(x, dict):
        raise JsonValueError(f"Expected JSON object, got {type(x).__name__}", ctx.get_path())

    validate_json_value(x, ctx=ctx)

def validate_json_array(x: object, *, ctx: JsonValueContext | None = None) -> None:
    """Validates that a value is a JSON array.

    Args:
        x: Value to validate.
        ctx: Optional validation context.

    Returns:
        ``None``.

    Raises:
        JsonValueError: Raised when ``x`` is not a valid JSON array.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)

    if not isinstance(x, list):
        raise JsonValueError(f"Expected JSON array, got {type(x).__name__}", ctx.get_path())

    validate_json_value(x, ctx=ctx)

def dump_convertible(convertible: JsonObjectConvertible, path: pathlib.Path, *, ctx: JsonValueContext | None = None) -> None:
    """Writes a convertible to a UTF-8 JSON file.

    The result of ``to_json_object()`` is validated before writing so that invalid JSON objects are rejected early.

    Args:
        convertible: Convertible to write.
        path: Destination file path.
        ctx: Optional validation context.

    Returns:
        ``None``.

    Raises:
        TypeError: Raised when serialization produces an invalid JSON object or when ``ctx`` is invalid.
        OSError: Raised when writing the file fails.
    """
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
    """Loads a convertible from a JSON file.

    Parsing rejects non-finite floats and invalid JSON constants before JSON object validation and deserialization begin.

    Args:
        cls: Target type to deserialize.
        path: Source file path.
        ctx: Optional validation context.

    Returns:
        The deserialized convertible.

    Raises:
        ValueError: Raised when JSON parsing fails.
        TypeError: Raised when the parsed value is not a valid JSON object, when deserialization fails, or when ``ctx`` is invalid.
        OSError: Raised when reading the file fails.
    """
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
    """Gets a string from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored string, or ``default`` if the key is missing or the value is invalid.
    """
    if key not in obj:
        return default

    value: object | None = obj[key]

    if not isinstance(value, str):
        return default

    return cast(str, value)

def get_int_from_json_object(obj: JsonObject, key: str, *, default: int = 0) -> int:
    """Gets an integer from a JSON object.

    Booleans are rejected explicitly.

    Args:
        obj: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored integer, or ``default`` if the key is missing or the value is invalid.
    """
    if key not in obj:
        return default

    value: object | None = obj[key]

    if isinstance(value, bool)\
        or (not isinstance(value, int)):
        return default

    return cast(int, value)

def get_float_from_json_object(obj: JsonObject, key: str, *, default: float = 0.0) -> float:
    """Gets a finite number from a JSON object as ``float``.

    Integers are accepted and converted to ``float``.
    Booleans and non-finite floats are rejected.

    Args:
        obj: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored number converted to ``float``, or ``default`` if the key is missing or the value is invalid.
    """
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
    """Gets a boolean from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored boolean, or ``default`` if the key is missing or the value is invalid.
    """
    if key not in obj:
        return default

    value: object | None = obj[key]

    if not isinstance(value, bool):
        return default

    return cast(bool, value)

def get_primitive_from_json_object(obj: JsonObject, key: str, *, default: JsonPrimitive = default_json_primitive(), ctx: JsonValueContext | None = None) -> JsonPrimitive:
    """Gets a JSON primitive from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.
        ctx: Optional validation context.

    Returns:
        The stored JSON primitive, or ``default`` if the key is missing or the value is invalid.

    Raises:
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Gets a JSON value from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.
        ctx: Optional validation context.

    Returns:
        The stored JSON value, or ``default`` if the key is missing or the value is invalid.

    Raises:
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Protocol for zero-argument factories that create default values."""

    def __call__(self) -> T_co:
        """Creates a default value.

        Returns:
            A newly created default value.
        """
        ...

def get_object_from_json_object(obj: JsonObject, key: str, *, default_factory: Factory[JsonObject] = dict, ctx: JsonValueContext | None = None) -> JsonObject:
    """Gets a JSON object from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        default_factory: Factory used to create the default object.
        ctx: Optional validation context.

    Returns:
        The stored JSON object, or a new default object if the key is missing or the value is invalid.

    Raises:
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Gets a JSON array from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        default_factory: Factory used to create the default array.
        ctx: Optional validation context.

    Returns:
        The stored JSON array, or a new default array if the key is missing or the value is invalid.

    Raises:
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Gets a convertible from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        cls: Target type to deserialize.
        default_factory: Factory used to create the default value.
        ctx: Optional validation context.

    Returns:
        The deserialized convertible, or a new default value if the key is missing, if the value is not a valid JSON object, or if deserialization fails.

    Raises:
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Gets a list of convertibles from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        cls: Target type used to deserialize each element.
        default_factory: Factory used to create the default list.
        ctx: Optional validation context.

    Returns:
        The deserialized convertibles, or a new default list if the key is missing, if the value is not a valid JSON array, if an element is not a valid JSON object, or if deserialization fails.

    Raises:
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Gets a required string from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        ctx: Optional validation context.

    Returns:
        The stored string.

    Raises:
        JsonValueError: Raised when the key is missing or when the value is not a string.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)

    if not isinstance(value, str):
        raise JsonValueError(f"Expected string, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_int_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> int:
    """Gets a required integer from a JSON object.

    Booleans are rejected explicitly.

    Args:
        obj: Source JSON object.
        key: Key to read.
        ctx: Optional validation context.

    Returns:
        The stored integer.

    Raises:
        JsonValueError: Raised when the key is missing or when the value is not an integer.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)

    if isinstance(value, bool) or (not isinstance(value, int)):
        raise JsonValueError(f"Expected integer, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_float_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> float:
    """Gets a required finite number from a JSON object as ``float``.

    Integers are accepted and converted to ``float``.
    Booleans and non-finite floats are rejected.

    Args:
        obj: Source JSON object.
        key: Key to read.
        ctx: Optional validation context.

    Returns:
        The stored number converted to ``float``.

    Raises:
        JsonValueError: Raised when the key is missing, when the value is not numeric, or when the value cannot be represented as a finite float.
        TypeError: Raised when ``ctx`` is invalid.
    """
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
    """Gets a required boolean from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        ctx: Optional validation context.

    Returns:
        The stored boolean.

    Raises:
        JsonValueError: Raised when the key is missing or when the value is not a boolean.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)

    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)

    if not isinstance(value, bool):
        raise JsonValueError(f"Expected boolean, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_primitive_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> JsonPrimitive:
    """Gets a required JSON primitive from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        ctx: Optional validation context.

    Returns:
        The stored JSON primitive.

    Raises:
        JsonValueError: Raised when the key is missing or when the value is not a valid JSON primitive.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_primitive(value, ctx=child_ctx)
    return cast(JsonPrimitive, value)

def require_value_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> JsonValue:
    """Gets a required JSON value from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        ctx: Optional validation context.

    Returns:
        The stored JSON value.

    Raises:
        JsonValueError: Raised when the key is missing or when the value is not a valid JSON value.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_value(value, ctx=child_ctx)
    return value

def require_object_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> JsonObject:
    """Gets a required JSON object from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        ctx: Optional validation context.

    Returns:
        The stored JSON object.

    Raises:
        JsonValueError: Raised when the key is missing or when the value is not a valid JSON object.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_object(value, ctx=child_ctx)
    return cast(JsonObject, value)

def require_array_from_json_object(obj: JsonObject, key: str, *, ctx: JsonValueContext | None = None) -> JsonArray:
    """Gets a required JSON array from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        ctx: Optional validation context.

    Returns:
        The stored JSON array.

    Raises:
        JsonValueError: Raised when the key is missing or when the value is not a valid JSON array.
        TypeError: Raised when ``ctx`` is invalid.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_array(value, ctx=child_ctx)
    return cast(JsonArray, value)

T = TypeVar("T", bound=JsonObjectConvertible)
def require_convertible_from_json_object(obj: JsonObject, key: str, cls: type[T], *, ctx: JsonValueContext | None = None) -> T:
    """Gets a required convertible from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        cls: Target type to deserialize.
        ctx: Optional validation context.

    Returns:
        The deserialized convertible.

    Raises:
        JsonValueError: Raised when the key is missing or when the stored value is not a valid JSON object.
        TypeError: Raised when ``ctx`` is invalid or when deserialization fails with a type-related error.
        ValueError: Raised when deserialization fails with a value-related error.
    """
    ctx: JsonValueContext = _normalize_json_value_context(ctx)
    child_ctx: JsonValueContext = ctx.create_child(key)
    value: object | None = _require_value_from_json_object(obj, key, ctx=ctx)
    validate_json_object(value, ctx=child_ctx)
    return cls.from_json_object(cast(JsonObject, value), ctx=child_ctx)

T = TypeVar("T", bound=JsonObjectConvertible)
def require_convertibles_from_json_object(obj: JsonObject, key: str, cls: type[T], *, ctx: JsonValueContext | None = None) -> list[T]:
    """Gets a required list of convertibles from a JSON object.

    Args:
        obj: Source JSON object.
        key: Key to read.
        cls: Target type used to deserialize each element.
        ctx: Optional validation context.

    Returns:
        The deserialized convertibles.

    Raises:
        JsonValueError: Raised when the key is missing, when the stored value is not a valid JSON array, or when an element is not a valid JSON object.
        TypeError: Raised when ``ctx`` is invalid or when element deserialization fails with a type-related error.
        ValueError: Raised when element deserialization fails with a value-related error.
    """
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
    """Converts convertibles to JSON objects.

    Each produced JSON object is validated with its element index as the root path so that failures point to the offending element.

    Args:
        convertibles: Convertibles to serialize.

    Returns:
        A list of validated JSON objects.

    Raises:
        TypeError: Raised when any element produces an invalid JSON object.
    """
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

# SPDX-FileCopyrightText: 2026 Iribo
# SPDX-License-Identifier: MIT

import abc
import enum
import json
import math
import pathlib
from typing import cast, ClassVar, Iterable, NoReturn, Optional, Protocol, TypeVar, Union

try:
    StrEnum = enum.StrEnum
except AttributeError:
    class StrEnum(str, enum.Enum):
        def __new__(cls: type["StrEnum"], *values: object) -> "StrEnum":
            if len(values) == 1:
                value = values[0]
            else:
                value = str(*values)

            if not isinstance(value, str):
                raise TypeError("StrEnum values must be str")

            obj: "StrEnum" = str.__new__(cls, value)
            obj._value_ = value
            return obj

        @staticmethod
        def _generate_next_value_(name: str, start: int, count: int, last_values: list[object]) -> str:
            return name.lower()

        def __str__(self) -> str:
            return str(self.value)

def _is_strict_int(x: object) -> bool:
    return type(x) is int

JsonPrimitive = Union[str, int, float, bool, None]
JsonObject = dict[str, "JsonValue"]
JsonArray = list["JsonValue"]
JsonValue = Union[JsonObject, JsonArray, JsonPrimitive]

JsonValuePathPart = Union[str, int]
JsonValuePath = tuple[JsonValuePathPart, ...]

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
    if _is_strict_int(x):
        if cast(int, x) < 0:
            raise ValueError(f"JsonValuePathPart integer must be >= 0, got {x}")

        return

    if isinstance(x, str):
        return

    raise TypeError(f"Invalid JsonValuePathPart: {type(x).__name__}")

def _validate_json_value_path(x: object) -> None:
    if not isinstance(x, tuple):
        raise TypeError(f"JsonValuePath must be tuple, got {type(x).__name__}")

    for part in cast(tuple[object, ...], x):
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

class JsonIssueSeverity(enum.Enum):
    """Severity level for a JSON issue."""
    ERROR = enum.auto()
    WARNING = enum.auto()
    NOTE = enum.auto()

class JsonIssueCode(enum.Enum):
    """Machine-readable code for a JSON issue."""
    MISSING_KEY = enum.auto()
    INVALID_TYPE = enum.auto()
    INVALID_VALUE = enum.auto()
    VALUE_CONVERSION_FAILED = enum.auto()
    DESERIALIZATION_FAILED = enum.auto()

class JsonIssue(object):
    """Structured information about a JSON-related issue worth keeping for later inspection."""

    def __init__(
        self,
        path: JsonValuePath,
        severity: JsonIssueSeverity,
        code: JsonIssueCode,
        message: str,
        value_type_name: Optional[str] = None,
        value_repr: Optional[str] = None,
        exception_type_name: Optional[str] = None,
        exception_message: Optional[str] = None,
    ):
        super(JsonIssue, self).__init__()

        _validate_json_value_path(path)

        self.__path: JsonValuePath = path
        self.__severity: JsonIssueSeverity = severity
        self.__code: JsonIssueCode = code
        self.__message: str = message
        self.__value_type_name: Optional[str] = value_type_name
        self.__value_repr: Optional[str] = value_repr
        self.__exception_type_name: Optional[str] = exception_type_name
        self.__exception_message: Optional[str] = exception_message

    def get_path(self) -> JsonValuePath:
        """Returns the JSON path associated with this issue."""
        return self.__path

    def get_severity(self) -> JsonIssueSeverity:
        """Returns the issue severity."""
        return self.__severity

    def get_code(self) -> JsonIssueCode:
        """Returns the issue code."""
        return self.__code

    def get_message(self) -> str:
        """Returns the human-readable message."""
        return self.__message

    def get_value_type_name(self) -> Optional[str]:
        """Returns the observed value type name, if available."""
        return self.__value_type_name

    def get_value_repr(self) -> Optional[str]:
        """Returns the formatted value representation, if available."""
        return self.__value_repr

    def get_exception_type_name(self) -> Optional[str]:
        """Returns the exception type name, if available."""
        return self.__exception_type_name

    def get_exception_message(self) -> Optional[str]:
        """Returns the exception message, if available."""
        return self.__exception_message

    def get_pointer(self) -> str:
        """Returns the issue path as a JSON Pointer-like string."""
        pointer: str = _json_value_path_to_pointer(self.get_path())
        return pointer if pointer else "<root>"

    def has_value(self) -> bool:
        """Returns whether this issue contains information about the observed value."""
        return self.__value_type_name is not None or self.__value_repr is not None

    def has_exception(self) -> bool:
        """Returns whether this issue contains exception information."""
        return self.__exception_type_name is not None or self.__exception_message is not None

    def matches_path_prefix(self, prefix: JsonValuePath) -> bool:
        """Returns whether the issue path starts with ``prefix``."""
        _validate_json_value_path(prefix)
        return self.__path[:len(prefix)] == prefix

    def to_full_message(self) -> str:
        """Formats the issue as a human-readable message."""
        parts: list[str] = [
            f"JSON issue at {self.get_pointer()}: {self.__message}",
            f"severity={self.__severity.name}",
            f"code={self.__code.name}",
        ]

        if self.__value_type_name is not None:
            parts.append(f"value_type={self.__value_type_name}")

        if self.__value_repr is not None:
            parts.append(f"value={self.__value_repr}")

        if self.__exception_type_name is not None:
            parts.append(f"exc_type={self.__exception_type_name}")

        if self.__exception_message is not None:
            parts.append(f"exc={self.__exception_message}")

        return "; ".join(parts)

    def __repr__(self) -> str:
        return (
            "JsonIssue("
            f"path={self.__path!r}, "
            f"severity={self.__severity!r}, "
            f"code={self.__code!r}, "
            f"message={self.__message!r}, "
            f"value_type_name={self.__value_type_name!r}, "
            f"value_repr={self.__value_repr!r}, "
            f"exception_type_name={self.__exception_type_name!r}, "
            f"exception_message={self.__exception_message!r})"
        )

    def __str__(self) -> str:
        return self.to_full_message()

def _validate_json_issue(x: object) -> None:
    if not isinstance(x, JsonIssue):
        raise TypeError(f"issue must be JsonIssue, got {type(x).__name__}")

def _validate_max_depth(x: object) -> None:
    if not _is_strict_int(x):
        raise TypeError(f"max_depth must be int, got {type(x).__name__}")

    if cast(int, x) < 0:
        raise ValueError(f"max_depth must be >= 0, got {x}")

def _validate_max_issue_value_repr_length(x: object) -> None:
    if x is None:
        return

    if not _is_strict_int(x):
        raise TypeError(f"max_issue_value_repr_length must be int or None, got {type(x).__name__}")

    if cast(int, x) < 0:
        raise ValueError(f"max_issue_value_repr_length must be >= 0, got {x}")

class JsonContext(object):
    """Stores the current JSON path, maximum validation depth, issue formatting settings, and a shared issue buffer."""

    def __init__(
        self,
        path: JsonValuePath = default_json_value_path(),
        max_depth: int = 1000,
        issues: Optional[list[JsonIssue]] = None,
        max_issue_value_repr_length: Optional[int] = 200,
    ):
        """Initializes a JSON context.

        Args:
            path: Current JSON value path.
            max_depth: Maximum allowed nesting depth for JSON values.
            issues: Shared issue buffer used to collect non-fatal JSON issues.
                If ``None``, a new empty buffer is created.
            max_issue_value_repr_length: Maximum length of ``JsonIssue.value_repr``.
                If ``None``, value representations are not truncated.

        Raises:
            TypeError: Raised when ``path``, ``max_depth``, or
                ``max_issue_value_repr_length`` has an invalid type, or when
                ``issues`` contains a non-``JsonIssue`` entry.
            ValueError: Raised when ``max_depth`` is negative, when
                ``max_issue_value_repr_length`` is negative, or when ``path``
                contains an invalid part.
        """
        super(JsonContext, self).__init__()

        _validate_json_value_path(path)
        _validate_max_depth(max_depth)
        _validate_max_issue_value_repr_length(max_issue_value_repr_length)

        if issues is None:
            issues = []

        for issue in issues:
            _validate_json_issue(issue)

        self.__path: JsonValuePath = path
        self.__max_depth: int = max_depth
        self.__issues: list[JsonIssue] = issues
        self.__max_issue_value_repr_length: Optional[int] = max_issue_value_repr_length

    def get_path(self) -> JsonValuePath:
        """Returns the current JSON path."""
        return self.__path

    def get_max_depth(self) -> int:
        """Returns the maximum validation depth."""
        return self.__max_depth

    def get_issues(self) -> list[JsonIssue]:
        """Returns the shared issue buffer."""
        return self.__issues

    def get_max_issue_value_repr_length(self) -> Optional[int]:
        """Returns the maximum length used for issue value representations."""
        return self.__max_issue_value_repr_length

    def add_issue(self, issue: JsonIssue) -> None:
        """Appends an issue to the shared issue buffer.

        Args:
            issue: Issue to append.

        Raises:
            TypeError: Raised when ``issue`` is not a ``JsonIssue``.
        """
        _validate_json_issue(issue)
        self.__issues.append(issue)

    def clear_issues(self) -> None:
        """Clears the shared issue buffer."""
        self.__issues.clear()

    def create_child(self, path_part: JsonValuePathPart) -> "JsonContext":
        """Creates a child context for a nested path part.

        The child context inherits the current maximum depth, issue formatting
        settings, and shared issue buffer.

        Args:
            path_part: Object key or array index to append to the current path.

        Returns:
            A new context for the child path.

        Raises:
            TypeError: Raised when ``path_part`` has an invalid type.
            ValueError: Raised when ``path_part`` is an invalid array index.
        """
        return JsonContext(
            path=append_json_value_path_part(self.get_path(), path_part),
            max_depth=self.get_max_depth(),
            issues=self.get_issues(),
            max_issue_value_repr_length=self.get_max_issue_value_repr_length(),
        )

_MISSING_ISSUE_VALUE: object = object()

def _get_exception_reason(exc: BaseException) -> str:
    if exc.args:
        try:
            return str(exc.args[0])
        except Exception:
            pass

    return exc.__class__.__name__

def _record_get_issue(
    ctx: JsonContext,
    code: JsonIssueCode,
    message: str,
    *,
    severity: JsonIssueSeverity = JsonIssueSeverity.WARNING,
    value: object = _MISSING_ISSUE_VALUE,
    exc: Optional[BaseException] = None,
) -> None:
    value_type_name: Optional[str] = None
    value_repr: Optional[str] = None

    if value is not _MISSING_ISSUE_VALUE:
        value_type_name = type(value).__name__

        try:
            value_repr = repr(value)
        except Exception as e:
            value_repr = f"<unrepresentable value ({type(e).__name__}: {e})>"

        max_length: Optional[int] = ctx.get_max_issue_value_repr_length()

        if ((max_length is not None)
            and (len(value_repr) > max_length)):
            if max_length <= 3:
                value_repr = value_repr[:max_length]
            else:
                value_repr = value_repr[:max_length - 3] + "..."

    exception_type_name: Optional[str] = None
    exception_message: Optional[str] = None

    if exc is not None:
        exception_type_name = type(exc).__name__
        exception_message = str(exc)

    ctx.add_issue(
        JsonIssue(
            path=ctx.get_path(),
            severity=severity,
            code=code,
            message=message,
            value_type_name=value_type_name,
            value_repr=value_repr,
            exception_type_name=exception_type_name,
            exception_message=exception_message,
        )
    )

T_JsonObjectConvertible = TypeVar("T_JsonObjectConvertible", bound="JsonObjectConvertible")
class JsonObjectConvertible(abc.ABC):
    """Abstract base class for objects that can be serialized to and deserialized from JSON objects."""

    @classmethod
    @abc.abstractmethod
    def from_json_object(cls: type[T_JsonObjectConvertible], ctx: JsonContext, json_object: JsonObject) -> T_JsonObjectConvertible:
        """Creates an instance from a JSON object.

        Args:
            ctx: Current JSON context, including the current path.
            json_object: Source JSON object.

        Returns:
            A newly created instance.

        Raises:
            JsonError: Raised when required JSON data is missing or when a JSON value is invalid.
            TypeError: Raised when deserialization encounters a type-related error.
            ValueError: Raised when deserialization encounters a value-related error.
        """
        ...

    @abc.abstractmethod
    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        """Converts this instance to a JSON object.

        Args:
            ctx: Current JSON context, including the current path.

        Returns:
            A JSON object representation of this instance.

        Raises:
            TypeError: Raised when serialization encounters a type-related error.
            ValueError: Raised when serialization encounters an invalid value.
        """
        ...

    @classmethod
    @abc.abstractmethod
    def create_default(cls: type[T_JsonObjectConvertible]) -> T_JsonObjectConvertible:
        """Creates a default instance of this type.

        Returns:
            A newly created default instance.
        """
        ...

T_Convertible = TypeVar("T_Convertible", bound=JsonObjectConvertible)

def _escape_json_pointer_part(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")

def _json_value_path_to_pointer(path: JsonValuePath) -> str:
    if not path:
        return ""

    parts: list[str] = []

    for part in path:
        if _is_strict_int(part):
            if cast(int, part) < 0:
                raise ValueError(f"Negative array index in JsonValuePath: {part}")

            parts.append(str(part))
        elif isinstance(part, str):
            parts.append(_escape_json_pointer_part(part))
        else:
            raise TypeError(f"Invalid JsonValuePathPart: {type(part).__name__}")

    return "/" + "/".join(parts)

def _format_json_location(path: JsonValuePath) -> str:
    pointer: str = _json_value_path_to_pointer(path)
    return pointer if pointer else "<root>"

class JsonError(ValueError):
    """Raised when a JSON-related validation or access error occurs under this module's rules."""

    def __init__(self, reason: str, path: JsonValuePath):
        """Initializes the error with a reason and a path.

        Args:
            reason: Human-readable description of the failure.
            path: Path at which the failure occurred.

        Raises:
            TypeError: Raised when ``path`` has an invalid type.
            ValueError: Raised when ``path`` contains an invalid part.
        """
        _validate_json_value_path(path)

        super(JsonError, self).__init__(reason)

        self.__path: JsonValuePath = path

    def get_path(self) -> JsonValuePath:
        """Returns the path associated with the error."""
        return self.__path

    def __str__(self) -> str:
        """Returns the error message including the path."""
        reason: str = _get_exception_reason(self)

        try:
            at: str = _format_json_location(self.__path)
        except Exception as e:
            try:
                path_repr = repr(self.__path)
            except Exception:
                path_repr = "<unrepresentable path>"

            at = f"<invalid path ({type(e).__name__}: {e}); path={path_repr}>"

        return f"{reason} at {at}"

T_IntEnum = TypeVar("T_IntEnum", bound=enum.IntEnum)
T_StrEnum = TypeVar("T_StrEnum", bound=StrEnum)

def validate_json_primitive(ctx: JsonContext, x: object) -> None:
    """Validates that a value is a JSON primitive.

    Accepted values are ``None``, ``bool``, ``str``, exact ``int`` objects, and finite ``float`` values.

    Args:
        ctx: Current JSON context, including the current path.
        x: Value to validate.

    Returns:
        ``None``.

    Raises:
        JsonError: Raised when ``x`` is not a valid JSON primitive under this module's rules.
    """
    if x is None:
        return

    if isinstance(x, bool):
        return

    if isinstance(x, str):
        return

    if _is_strict_int(x):
        return

    if isinstance(x, float):
        if math.isfinite(x):
            return

        raise JsonError(f"Non-finite float: {x!r}", ctx.get_path())

    raise JsonError(f"Expected JSON primitive, got {type(x).__name__}", ctx.get_path())

class _StackItem(object):
    DUMMY_OID: ClassVar[int] = -1
    DUMMY_VALUE: ClassVar[object] = object()

    def __init__(self, discard: bool, oid: int, value: object, depth: int, path: JsonValuePath):
        self.__discard: bool = discard
        self.__oid: int = oid
        self.__value: object = value
        self.__depth: int = depth
        self.__path: JsonValuePath = path

    def get_discard(self) -> bool:
        return self.__discard

    def get_oid(self) -> int:
        return self.__oid

    def get_value(self) -> object:
        return self.__value

    def get_depth(self) -> int:
        return self.__depth

    def get_path(self) -> JsonValuePath:
        return self.__path

def validate_json_value(ctx: JsonContext, x: object) -> None:
    """Validates that a value is a JSON value.

    This validator traverses nested objects and arrays iteratively, enforces a maximum nesting depth, rejects non-string object keys, and detects cycles in container graphs.

    Args:
        ctx: Current JSON context, including the current path.
        x: Value to validate.

    Returns:
        ``None``.

    Raises:
        JsonError: Raised when ``x`` is not a valid JSON value.
    """
    active_oids: set[int] = set()
    stack: list[_StackItem] = [_StackItem(False, _StackItem.DUMMY_OID, x, 0, ctx.get_path())]

    while stack:
        item: _StackItem = stack.pop()

        if item.get_discard():
            active_oids.discard(item.get_oid())
            continue

        if item.get_depth() > ctx.get_max_depth():
            raise JsonError(f"JSON max depth exceeded: depth={item.get_depth()} > max_depth={ctx.get_max_depth()}", item.get_path())

        if isinstance(item.get_value(), dict):
            # Pylance strict cannot infer the precise type here.
            # This cast is intentional; container contents are validated below at runtime.
            obj: dict = cast(dict, item.get_value())

            oid = id(obj)

            if oid in active_oids:
                raise JsonError("Cycle detected (object)", item.get_path())

            active_oids.add(oid)
            stack.append(_StackItem(True, oid, _StackItem.DUMMY_VALUE, item.get_depth(), item.get_path()))

            items: list[tuple[object, object]] = list(obj.items())

            for k, v in reversed(items):
                if not isinstance(k, str):
                    raise JsonError(f"Non-string object key: {k!r} (type={type(k).__name__})", item.get_path())

                child_path: JsonValuePath = append_json_value_path_part(item.get_path(), k)
                stack.append(_StackItem(False, _StackItem.DUMMY_OID, v, item.get_depth() + 1, child_path))

        elif isinstance(item.get_value(), list):
            # Pylance strict cannot infer the precise type here.
            # This cast is intentional; container contents are validated below at runtime.
            array: list = cast(list, item.get_value())

            oid = id(array)

            if oid in active_oids:
                raise JsonError("Cycle detected (array)", item.get_path())

            active_oids.add(oid)
            stack.append(_StackItem(True, oid, _StackItem.DUMMY_VALUE, item.get_depth(), item.get_path()))

            for i in range(len(array) - 1, -1, -1):
                child_path: JsonValuePath = append_json_value_path_part(item.get_path(), i)
                stack.append(_StackItem(False, _StackItem.DUMMY_OID, array[i], item.get_depth() + 1, child_path))

        else:
            validate_json_primitive(
                JsonContext(
                    path=item.get_path(),
                    max_depth=ctx.get_max_depth(),
                    issues=ctx.get_issues(),
                    max_issue_value_repr_length=ctx.get_max_issue_value_repr_length()
                ),
                item.get_value()
            )

def validate_json_object(ctx: JsonContext, x: object) -> None:
    """Validates that a value is a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        x: Value to validate.

    Returns:
        ``None``.

    Raises:
        JsonError: Raised when ``x`` is not a valid JSON object.
    """
    if not isinstance(x, dict):
        raise JsonError(f"Expected JSON object, got {type(x).__name__}", ctx.get_path())

    # Pylance strict cannot infer the precise type here.
    # Container type is checked above; full validation is delegated to validate_json_value().
    validate_json_value(ctx, x)

def validate_json_array(ctx: JsonContext, x: object) -> None:
    """Validates that a value is a JSON array.

    Args:
        ctx: Current JSON context, including the current path.
        x: Value to validate.

    Returns:
        ``None``.

    Raises:
        JsonError: Raised when ``x`` is not a valid JSON array.
    """
    if not isinstance(x, list):
        raise JsonError(f"Expected JSON array, got {type(x).__name__}", ctx.get_path())

    # Pylance strict cannot infer the precise type here.
    # Container type is checked above; full validation is delegated to validate_json_value().
    validate_json_value(ctx, x)

def dump_convertible(ctx: JsonContext, convertible: JsonObjectConvertible, path: pathlib.Path) -> None:
    """Writes an object to a UTF-8 JSON file.

    The JSON object returned by ``to_json_object()`` is validated before writing.
    Exceptions raised directly by ``to_json_object()`` are propagated unchanged.

    Args:
        ctx: Current JSON context, including the current path.
        convertible: Object to serialize.
        path: Destination file path.

    Returns:
        ``None``.

    Raises:
        TypeError: Raised when ``to_json_object()`` returns an invalid JSON object.
        OSError: Raised when writing the file fails.
    """
    o: JsonObject = convertible.to_json_object(ctx)

    try:
        validate_json_object(ctx, o)
    except JsonError as e:
        raise TypeError(f"Invalid JSON object produced by {type(convertible).__name__} for {path}: {e}") from e

    s: str = json.dumps(o, ensure_ascii=False, allow_nan=False, indent=4, sort_keys=True)
    path.write_text(s, encoding="utf-8")

def _parse_float(s: str) -> float:
    f: float = float(s)

    if not math.isfinite(f):
        raise ValueError(f"Non-finite float: {s!r}")

    return f

def _parse_constant(s: str) -> NoReturn:
    raise ValueError(f"Invalid JSON constant: {s}")

T = TypeVar("T", bound=JsonObjectConvertible)
def load_convertible(ctx: JsonContext, cls: type[T], path: pathlib.Path) -> T:
    """Loads and deserializes an object from a JSON file.

    Parsing rejects non-finite floats and invalid JSON constants before validation and deserialization begin.
    Deserialization failures are normalized to ``TypeError``.

    Args:
        ctx: Current JSON context, including the current path.
        cls: Target type to deserialize.
        path: Source file path.

    Returns:
        The deserialized instance.

    Raises:
        ValueError: Raised when JSON parsing fails.
        TypeError: Raised when the parsed value is not a valid JSON object or when deserialization fails.
        OSError: Raised when reading the file fails.
    """
    s: str = path.read_text(encoding="utf-8")

    try:
        o = json.loads(s, parse_float=_parse_float, parse_constant=_parse_constant)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Failed to parse JSON from {path}: {e}") from e

    try:
        validate_json_object(ctx, o)
    except JsonError as e:
        raise TypeError(f"Invalid JSON object in {path}: {e}") from e

    try:
        return cls.from_json_object(ctx, cast(JsonObject, o))
    except (JsonError, TypeError, ValueError) as e:
        raise TypeError(f"Failed to deserialize {cls.__name__} from {path}: {e}") from e

def get_str(ctx: JsonContext, json_object: JsonObject, key: str, *, default: str = "") -> str:
    """Gets a string from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored string, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default

    value: object = json_object[key]

    if not isinstance(value, str):
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_TYPE, f"Expected string, got {type(value).__name__}", value=value)
        return default

    return value

def get_int(ctx: JsonContext, json_object: JsonObject, key: str, *, default: int = 0) -> int:
    """Gets an integer from a JSON object.

    Only exact ``int`` objects are accepted.
    ``bool`` and integer subclasses are rejected.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored integer, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default

    value: object = json_object[key]

    if not _is_strict_int(value):
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_TYPE, f"Expected integer, got {type(value).__name__}", value=value)
        return default

    return cast(int, value)

def get_float(ctx: JsonContext, json_object: JsonObject, key: str, *, default: float = 0.0) -> float:
    """Gets a finite number from a JSON object as ``float``.

    Integers are accepted and converted to ``float``.
    Booleans and non-finite floats are rejected.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored number converted to ``float``, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default

    value: object = json_object[key]

    if _is_strict_int(value):
        try:
            return float(cast(int, value))
        except OverflowError as e:
            _record_get_issue(child_ctx, JsonIssueCode.VALUE_CONVERSION_FAILED, "Integer too large to convert to float", value=value, exc=e)
            return default

    if isinstance(value, float):
        if math.isfinite(value):
            return value

        _record_get_issue(child_ctx, JsonIssueCode.INVALID_VALUE, "Non-finite float", value=value)
        return default

    _record_get_issue(child_ctx, JsonIssueCode.INVALID_TYPE, f"Expected number, got {type(value).__name__}", value=value)
    return default

def get_bool(ctx: JsonContext, json_object: JsonObject, key: str, *, default: bool = False) -> bool:
    """Gets a boolean from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored boolean, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default

    value: object = json_object[key]

    if not isinstance(value, bool):
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_TYPE, f"Expected boolean, got {type(value).__name__}", value=value)
        return default

    return value

def get_primitive(ctx: JsonContext, json_object: JsonObject, key: str, *, default: JsonPrimitive = default_json_primitive()) -> JsonPrimitive:
    """Gets a JSON primitive stored under a key.

    The stored value must satisfy this module's JSON primitive rules.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored JSON primitive, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default

    value: object = json_object[key]

    try:
        validate_json_primitive(child_ctx, value)
    except JsonError as e:
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=value, exc=e)
        return default

    return cast(JsonPrimitive, value)

def get_value(ctx: JsonContext, json_object: JsonObject, key: str, *, default: JsonValue = default_json_value()) -> JsonValue:
    """Gets a JSON value stored under a key.

    The stored value must satisfy this module's JSON value rules.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default: Default value to return when the key is missing or the value is invalid.

    Returns:
        The stored JSON value, or ``default`` if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default

    value: object = json_object[key]

    try:
        validate_json_value(child_ctx, value)
    except JsonError as e:
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=value, exc=e)
        return default

    return cast(JsonValue, value)

T_co = TypeVar("T_co", covariant=True)
class Factory(Protocol[T_co]):
    """Protocol for zero-argument factories that create default values."""

    def __call__(self) -> T_co:
        """Creates a default value."""
        ...

def get_object(ctx: JsonContext, json_object: JsonObject, key: str, *, default_factory: Factory[JsonObject] = default_json_object) -> JsonObject:
    """Gets a JSON object stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default_factory: Factory used to create the default object.

    Returns:
        The stored JSON object, or a new default object if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default_factory()

    value: object = json_object[key]

    try:
        validate_json_object(child_ctx, value)
    except JsonError as e:
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=value, exc=e)
        return default_factory()

    return cast(JsonObject, value)

def get_array(ctx: JsonContext, json_object: JsonObject, key: str, *, default_factory: Factory[JsonArray] = default_json_array) -> JsonArray:
    """Gets a JSON array stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        default_factory: Factory used to create the default array.

    Returns:
        The stored JSON array, or a new default array if the key is missing or the value is invalid.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default_factory()

    value: object = json_object[key]

    try:
        validate_json_array(child_ctx, value)
    except JsonError as e:
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=value, exc=e)
        return default_factory()

    return cast(JsonArray, value)

def get_convertible(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_Convertible], *, default_factory: Optional[Factory[T_Convertible]] = None) -> T_Convertible:
    """Gets and deserializes an object from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        cls: Target type to deserialize.
        default_factory: Factory used to create the default instance.
            If ``None``, ``cls.create_default`` is used.

    Returns:
        The deserialized instance, or a new default instance if the key is missing,
        if the value is not a valid JSON object, or if deserialization fails.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    factory: Factory[T_Convertible] = cls.create_default if default_factory is None else default_factory

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return factory()

    value: object = json_object[key]

    try:
        validate_json_object(child_ctx, value)
    except JsonError as e:
        error_ctx: JsonContext = JsonContext(
            path=e.get_path(),
            max_depth=ctx.get_max_depth(),
            issues=ctx.get_issues(),
            max_issue_value_repr_length=ctx.get_max_issue_value_repr_length(),
        )

        issue_value: object = value if e.get_path() == child_ctx.get_path() else _MISSING_ISSUE_VALUE
        _record_get_issue(error_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=issue_value, exc=e)
        return factory()

    try:
        return cls.from_json_object(child_ctx, cast(JsonObject, value))
    except JsonError as e:
        error_ctx = JsonContext(
            path=e.get_path(),
            max_depth=ctx.get_max_depth(),
            issues=ctx.get_issues(),
            max_issue_value_repr_length=ctx.get_max_issue_value_repr_length(),
        )

        issue_value = value if e.get_path() == child_ctx.get_path() else _MISSING_ISSUE_VALUE
        _record_get_issue(error_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=issue_value, exc=e)
        return factory()
    except (TypeError, ValueError) as e:
        _record_get_issue(child_ctx, JsonIssueCode.DESERIALIZATION_FAILED, f"Failed to deserialize {cls.__name__}", value=value, exc=e)
        return factory()

def get_convertibles(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_Convertible], *, default_factory: Factory[list[T_Convertible]] = list) -> list[T_Convertible]:
    """Gets and deserializes a list of objects from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        cls: Target type used to deserialize each element.
        default_factory: Factory used to create the default list.

    Returns:
        The deserialized instances, or a new default list if the key is missing,
        if the value is not a valid JSON array, if an element is not a valid JSON object,
        or if deserialization fails.
    """
    array_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(array_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default_factory()

    value: object = json_object[key]

    try:
        validate_json_array(array_ctx, value)
    except JsonError as e:
        _record_get_issue(array_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=value, exc=e)
        return default_factory()

    convertibles: list[T_Convertible] = []

    for i, item in enumerate(cast(JsonArray, value)):
        item_ctx: JsonContext = array_ctx.create_child(i)

        try:
            validate_json_object(item_ctx, item)
        except JsonError as e:
            error_ctx: JsonContext = JsonContext(
                path=e.get_path(),
                max_depth=ctx.get_max_depth(),
                issues=ctx.get_issues(),
                max_issue_value_repr_length=ctx.get_max_issue_value_repr_length(),
            )

            issue_value: object = item if e.get_path() == item_ctx.get_path() else _MISSING_ISSUE_VALUE
            _record_get_issue(error_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=issue_value, exc=e)
            return default_factory()

        try:
            convertible: T_Convertible = cls.from_json_object(item_ctx, cast(JsonObject, item))
        except JsonError as e:
            error_ctx = JsonContext(
                path=e.get_path(),
                max_depth=ctx.get_max_depth(),
                issues=ctx.get_issues(),
                max_issue_value_repr_length=ctx.get_max_issue_value_repr_length(),
            )

            issue_value = item if e.get_path() == item_ctx.get_path() else _MISSING_ISSUE_VALUE
            _record_get_issue(error_ctx, JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), value=issue_value, exc=e)
            return default_factory()
        except (TypeError, ValueError) as e:
            _record_get_issue(item_ctx, JsonIssueCode.DESERIALIZATION_FAILED, f"Failed to deserialize {cls.__name__}", value=item, exc=e)
            return default_factory()

        convertibles.append(convertible)

    return convertibles

def get_int_enum(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_IntEnum], *, default: T_IntEnum) -> T_IntEnum:
    """Gets an ``IntEnum`` member from a JSON object.

    Only exact ``int`` objects are accepted.
    ``bool`` and integer subclasses are rejected.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default

    value: object = json_object[key]

    if not _is_strict_int(value):
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_TYPE, f"Expected integer, got {type(value).__name__}", value=value)
        return default

    try:
        return cls(cast(int, value))
    except ValueError as e:
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_VALUE, f"Invalid {cls.__name__} value: {value!r}", value=value, exc=e)
        return default

def get_str_enum(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_StrEnum], *, default: T_StrEnum) -> T_StrEnum:
    """Gets a ``StrEnum`` member from a JSON object."""
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return default

    value: object = json_object[key]

    if not isinstance(value, str):
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_TYPE, f"Expected string, got {type(value).__name__}", value=value)
        return default

    try:
        return cls(value)
    except ValueError as e:
        _record_get_issue(child_ctx, JsonIssueCode.INVALID_VALUE, f"Invalid {cls.__name__} value: {value!r}", value=value, exc=e)
        return default

def _require_value(ctx: JsonContext, json_object: JsonObject, key: str) -> object:
    child_ctx: JsonContext = ctx.create_child(key)

    if key not in json_object:
        raise JsonError("Missing required key", child_ctx.get_path())

    return json_object[key]

def require_str(ctx: JsonContext, json_object: JsonObject, key: str) -> str:
    """Gets a required string from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored string.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a string.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    value: object = _require_value(ctx, json_object, key)

    if not isinstance(value, str):
        raise JsonError(f"Expected string, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_int(ctx: JsonContext, json_object: JsonObject, key: str) -> int:
    """Gets a required integer from a JSON object.

    Only exact ``int`` objects are accepted.
    ``bool`` and integer subclasses are rejected.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored integer.

    Raises:
        JsonError: Raised when the key is missing or when the value is not an integer.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    value: object = _require_value(ctx, json_object, key)

    if not _is_strict_int(value):
        raise JsonError(f"Expected integer, got {type(value).__name__}", child_ctx.get_path())

    return cast(int, value)

def require_float(ctx: JsonContext, json_object: JsonObject, key: str) -> float:
    """Gets a required finite number from a JSON object as ``float``.

    Integers are accepted and converted to ``float``.
    Booleans and non-finite floats are rejected.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored number converted to ``float``.

    Raises:
        JsonError: Raised when the key is missing, when the value is not numeric, or when the value cannot be represented as a finite float.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    value: object = _require_value(ctx, json_object, key)

    if _is_strict_int(value):
        try:
            return float(cast(int, value))
        except OverflowError:
            raise JsonError(f"Integer too large to convert to float: {value!r}", child_ctx.get_path())

    if isinstance(value, float):
        if math.isfinite(value):
            return value
        else:
            raise JsonError(f"Non-finite float: {value!r}", child_ctx.get_path())

    raise JsonError(f"Expected number, got {type(value).__name__}", child_ctx.get_path())

def require_bool(ctx: JsonContext, json_object: JsonObject, key: str) -> bool:
    """Gets a required boolean from a JSON object.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored boolean.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a boolean.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    value: object = _require_value(ctx, json_object, key)

    if not isinstance(value, bool):
        raise JsonError(f"Expected boolean, got {type(value).__name__}", child_ctx.get_path())

    return value

def require_primitive(ctx: JsonContext, json_object: JsonObject, key: str) -> JsonPrimitive:
    """Gets a required JSON primitive stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored JSON primitive.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a valid JSON primitive.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_primitive(child_ctx, value)
    return cast(JsonPrimitive, value)

def require_value(ctx: JsonContext, json_object: JsonObject, key: str) -> JsonValue:
    """Gets a required JSON value stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored JSON value.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a valid JSON value.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_value(child_ctx, value)
    return cast(JsonValue, value)

def require_object(ctx: JsonContext, json_object: JsonObject, key: str) -> JsonObject:
    """Gets a required JSON object stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored JSON object.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a valid JSON object.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_object(child_ctx, value)
    return cast(JsonObject, value)

def require_array(ctx: JsonContext, json_object: JsonObject, key: str) -> JsonArray:
    """Gets a required JSON array stored under a key.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.

    Returns:
        The stored JSON array.

    Raises:
        JsonError: Raised when the key is missing or when the value is not a valid JSON array.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_array(child_ctx, value)
    return cast(JsonArray, value)

def require_convertible(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_Convertible]) -> T_Convertible:
    """Gets and deserializes a required object from a JSON object.

    Deserialization errors are propagated as raised by ``cls.from_json_object()``.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        cls: Target type to deserialize.

    Returns:
        The deserialized instance.

    Raises:
        JsonError: Raised when the key is missing or when the stored value is not a valid JSON object.
        TypeError: Raised when deserialization fails with a type-related error.
        ValueError: Raised when deserialization fails with a value-related error.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)
    validate_json_object(child_ctx, value)
    return cls.from_json_object(child_ctx, cast(JsonObject, value))

def require_convertibles(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_Convertible]) -> list[T_Convertible]:
    """Gets and deserializes a required list of objects from a JSON object.

    Element deserialization errors are propagated as raised by ``cls.from_json_object()``.

    Args:
        ctx: Current JSON context, including the current path.
        json_object: Source JSON object.
        key: Key to read.
        cls: Target type used to deserialize each element.

    Returns:
        The deserialized instances.

    Raises:
        JsonError: Raised when the key is missing, when the stored value is not a valid JSON array, or when an element is not a valid JSON object.
        TypeError: Raised when element deserialization fails with a type-related error.
        ValueError: Raised when element deserialization fails with a value-related error.
    """
    value: object = _require_value(ctx, json_object, key)

    array_ctx: JsonContext = ctx.create_child(key)
    validate_json_array(array_ctx, value)

    convertibles: list[T_Convertible] = []

    for i, item in enumerate(cast(JsonArray, value)):
        item_ctx: JsonContext = array_ctx.create_child(i)
        validate_json_object(item_ctx, item)
        convertibles.append(cls.from_json_object(item_ctx, cast(JsonObject, item)))

    return convertibles

def require_int_enum(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_IntEnum]) -> T_IntEnum:
    """Gets a required ``IntEnum`` member from a JSON object.

    Only exact ``int`` objects are accepted.
    ``bool`` and integer subclasses are rejected.
    """
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)

    if not _is_strict_int(value):
        raise JsonError(f"Expected integer, got {type(value).__name__}", child_ctx.get_path())

    try:
        return cls(cast(int, value))
    except ValueError:
        raise JsonError(f"Invalid {cls.__name__} value: {value!r}", child_ctx.get_path())

def require_str_enum(ctx: JsonContext, json_object: JsonObject, key: str, cls: type[T_StrEnum]) -> T_StrEnum:
    """Gets a required ``StrEnum`` member from a JSON object."""
    child_ctx: JsonContext = ctx.create_child(key)
    value: object = _require_value(ctx, json_object, key)

    if not isinstance(value, str):
        raise JsonError(f"Expected string, got {type(value).__name__}", child_ctx.get_path())

    try:
        return cls(value)
    except ValueError:
        raise JsonError(f"Invalid {cls.__name__} value: {value!r}", child_ctx.get_path())

def convert_convertible_to_json_object(ctx: JsonContext, key: str, convertible: JsonObjectConvertible) -> JsonObject:
    """Converts an object to a validated JSON object.

    The object returned by ``to_json_object()`` is validated with ``key`` appended to ``ctx`` so that failures point to the correct location.
    Exceptions raised directly by ``to_json_object()`` are propagated unchanged.

    Args:
        ctx: Current JSON context, including the current path.
        key: Key associated with the object in the parent JSON object.
        convertible: Object to serialize.

    Returns:
        A validated JSON object.

    Raises:
        TypeError: Raised when the produced value is not a valid JSON object.
        ValueError: Raised when ``to_json_object()`` fails with an invalid value.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    json_object: JsonObject = convertible.to_json_object(child_ctx)

    try:
        validate_json_object(child_ctx, json_object)
    except JsonError as e:
        raise TypeError(f"Invalid JSON object produced by {type(convertible).__name__} for key {key!r}: {e}") from e

    return json_object

def convert_convertibles_to_json_objects(ctx: JsonContext, key: str, convertibles: Iterable[JsonObjectConvertible]) -> list[JsonObject]:
    """Converts an iterable of objects to validated JSON objects.

    Each object returned by ``to_json_object()`` is validated with both ``key`` and the element index appended to ``ctx`` so that failures point to the offending element.
    Exceptions raised directly by ``to_json_object()`` are propagated unchanged.

    Args:
        ctx: Current JSON context, including the current path.
        key: Key associated with the object list in the parent JSON object.
        convertibles: Objects to serialize.

    Returns:
        A list of validated JSON objects.

    Raises:
        TypeError: Raised when any produced value is not a valid JSON object.
        ValueError: Raised when element serialization fails with an invalid value.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    json_objects: list[JsonObject] = []

    for i, convertible in enumerate(convertibles):
        item_ctx: JsonContext = child_ctx.create_child(i)
        json_object: JsonObject = convertible.to_json_object(item_ctx)

        try:
            validate_json_object(item_ctx, json_object)
        except JsonError as e:
            raise TypeError(f"Invalid JSON object produced by element {i} ({type(convertible).__name__}) for key {key!r}: {e}") from e

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
    "JsonError",
    "validate_json_primitive",
    "validate_json_value",
    "validate_json_object",
    "validate_json_array",
    "JsonObjectConvertible",
    "dump_convertible",
    "load_convertible",
    "get_str",
    "get_int",
    "get_float",
    "get_bool",
    "get_primitive",
    "get_value",
    "Factory",
    "get_object",
    "get_array",
    "get_convertible",
    "get_convertibles",
    "require_str",
    "require_int",
    "require_float",
    "require_bool",
    "require_primitive",
    "require_value",
    "require_object",
    "require_array",
    "require_convertible",
    "require_convertibles",
    "convert_convertible_to_json_object",
    "convert_convertibles_to_json_objects",
    "append_json_value_path_part",
    "JsonContext",
    "JsonIssueSeverity",
    "JsonIssueCode",
    "JsonIssue",
    "StrEnum",
    "get_enum",
    "get_int_enum",
    "get_str_enum",
    "require_enum",
    "require_int_enum",
    "require_str_enum",
]

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
        """Initializes a JSON issue record.

        Args:
            path: JSON path at which the issue occurred.
            severity: Severity level of the issue.
            code: Machine-readable issue code.
            message: Human-readable description of the issue.
            value_type_name: Observed value type name, if available.
            value_repr: Formatted value representation, if available.
            exception_type_name: Exception type name, if available.
            exception_message: Exception message, if available.

        Raises:
            TypeError: Raised when ``path`` has an invalid type.
            ValueError: Raised when ``path`` contains an invalid part.
        """
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

    def to_detail_message(self) -> str:
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
            parts.append(f"exception_type={self.__exception_type_name}")

        if self.__exception_message is not None:
            parts.append(f"exception={self.__exception_message}")

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
        return self.to_detail_message()

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
        use_shallow_validation: bool = False
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
        self.__use_shallow_validation: bool = use_shallow_validation

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

    def get_use_shallow_validation(self) -> bool:
        return self.__use_shallow_validation

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
            use_shallow_validation=self.get_use_shallow_validation()
        )

    def create_with_use_shallow_validation(self, use: bool) -> "JsonContext":
        return JsonContext(
            path=self.get_path(),
            max_depth=self.get_max_depth(),
            issues=self.get_issues(),
            max_issue_value_repr_length=self.get_max_issue_value_repr_length(),
            use_shallow_validation=use
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


def _validate_json_object_shallow(ctx: JsonContext, x: object) -> None:
    if not isinstance(x, dict):
        raise JsonError(f"Expected JSON object, got {type(x).__name__}", ctx.get_path())

    for k in cast(dict[object, object], x).keys():
        if not isinstance(k, str):
            raise JsonError(f"Non-string object key: {k!r} (type={type(k).__name__})", ctx.get_path())


def _validate_json_array_shallow(ctx: JsonContext, x: object) -> None:
    if not isinstance(x, list):
        raise JsonError(f"Expected JSON array, got {type(x).__name__}", ctx.get_path())


def _validate_json_primitive_shallow(ctx: JsonContext, x: object) -> None:
    validate_json_primitive(ctx, x)


def _validate_json_value_shallow(ctx: JsonContext, x: object) -> None:
    if isinstance(x, dict):
        _validate_json_object_shallow(ctx, x)
        return

    if isinstance(x, list):
        _validate_json_array_shallow(ctx, x)
        return

    _validate_json_primitive_shallow(ctx, x)


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
        TypeError: Raised when ``to_json_object()`` returns an invalid JSON object,
            plus any ``TypeError`` raised directly by ``to_json_object()``.
        ValueError: Raised when ``to_json_object()`` fails with an invalid value.
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

    validated_ctx: JsonContext = ctx.create_with_use_shallow_validation(True)

    try:
        return cls.from_json_object(validated_ctx, cast(JsonObject, o))
    except (JsonError, TypeError, ValueError) as e:
        raise TypeError(f"Failed to deserialize {cls.__name__} from {path}: {e}") from e

T_co = TypeVar("T_co", covariant=True)
class Factory(Protocol[T_co]):
    """Protocol for zero-argument factories that create default values."""

    def __call__(self) -> T_co:
        """Creates a default value."""
        ...


class GetIssueInfo(object):
    def __init__(self,
        path: JsonValuePath,
        code: JsonIssueCode,
        message: str,
        value: object,
        exc: Optional[BaseException] = None):

        super(GetIssueInfo, self).__init__()

        self.__path: JsonValuePath = path
        self.__code: JsonIssueCode = code
        self.__message: str = message
        self.__value: object = value
        self.__exc: Optional[BaseException] = exc


    def get_path(self) -> JsonValuePath:
        return self.__path


    def get_code(self) -> JsonIssueCode:
        return self.__code


    def get_message(self) -> str:
        return self.__message


    def get_value(self) -> object:
        return self.__value


    def get_exc(self) -> Optional[BaseException]:
        return self.__exc


    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"path={self.__path!r}, "
            f"code={self.__code!r}, "
            f"message={self.__message!r}, "
            f"value={self.__value!r}, "
            f"exc={self.__exc!r})"
        )


def _normalize_type_or_types(type_or_types: object) -> tuple[object, ...]:
    if isinstance(type_or_types, tuple):
        return cast(tuple[object, ...], type_or_types)

    return (type_or_types,)


_MISSING_DEFAULT: object = object()


class ArrayOf(object):
    def __init__(self, *element_types: object):
        if not element_types:
            raise ValueError("ArrayOf requires at least one element type")

        self.__element_types: object = element_types[0] if len(element_types) == 1 else element_types


    def get_element_types(self) -> object:
        return self.__element_types


    def __repr__(self) -> str:
        return f"ArrayOf({self.__element_types!r})"


class ValuesOf(object):
    def __init__(self, *value_types: object):
        if not value_types:
            raise ValueError("ValuesOf requires at least one value type")

        self.__value_types: object = value_types[0] if len(value_types) == 1 else value_types


    def get_value_types(self) -> object:
        return self.__value_types


    def __repr__(self) -> str:
        return f"ValuesOf({self.__value_types!r})"


def _resolve_default_value(default: object, types: tuple[object, ...]) -> object:
    if default is not _MISSING_DEFAULT:
        if callable(default):
            return cast(Factory[object], default)()
        return default

    first_type: object = types[0]

    if isinstance(first_type, ArrayOf):
        return []

    if isinstance(first_type, ValuesOf):
        return {}

    if first_type is str:
        return ""

    if first_type is int:
        return 0

    if first_type is float:
        return 0.0

    if first_type is bool:
        return False

    if first_type is JsonPrimitive:
        return default_json_primitive()

    if first_type is JsonObject:
        return default_json_object()

    if first_type is JsonArray:
        return default_json_array()

    if first_type is JsonValue:
        return default_json_value()

    if isinstance(first_type, type) and issubclass(first_type, enum.IntEnum):
        try:
            return next(iter(first_type))
        except StopIteration:
            raise TypeError(f"Cannot infer default for empty enum: {first_type!r}")

    if isinstance(first_type, type) and issubclass(first_type, StrEnum):
        try:
            return next(iter(first_type))
        except StopIteration:
            raise TypeError(f"Cannot infer default for empty enum: {first_type!r}")

    if isinstance(first_type, type) and issubclass(first_type, JsonObjectConvertible):
        return first_type.create_default()

    raise TypeError(f"Unsupported get type: {first_type!r}")


def _try_read_value_as_types(ctx: JsonContext, value: object, types: tuple[object, ...]) -> tuple[bool, object, Optional[GetIssueInfo]]:
    if not types:
        raise ValueError("types must not be empty")

    if len(types) > 1:
        errors: list[GetIssueInfo] = []

        for t in types:
            ok, result, error = _try_read_value_as_types(ctx, value, (t,))

            if ok:
                return True, result, None

            if error is not None:
                errors.append(error)

        best_error: Optional[GetIssueInfo] = None

        for error in errors:
            if best_error is None:
                best_error = error
                continue

            if len(error.get_path()) > len(best_error.get_path()):
                best_error = error
                continue

            if ((len(error.get_path()) == len(best_error.get_path()))
                and (best_error.get_code() == JsonIssueCode.INVALID_TYPE)
                and (error.get_code() != JsonIssueCode.INVALID_TYPE)):
                best_error = error

        if best_error is None:
            raise AssertionError("Unreachable: type candidates produced no result and no error")

        if len(best_error.get_path()) > len(ctx.get_path()):
            return False, None, best_error

        expected_type_names: list[str] = []

        for t in types:
            if isinstance(t, ArrayOf):
                expected_type_names.append(f"ArrayOf({t.get_element_types()!r})")

            elif isinstance(t, ValuesOf):
                expected_type_names.append(f"ValuesOf({t.get_value_types()!r})")

            elif t is str:
                expected_type_names.append("string")

            elif t is int:
                expected_type_names.append("integer")

            elif t is float:
                expected_type_names.append("number")

            elif t is bool:
                expected_type_names.append("boolean")

            elif t is JsonPrimitive:
                expected_type_names.append("JsonPrimitive")

            elif t is JsonObject:
                expected_type_names.append("JsonObject")

            elif t is JsonArray:
                expected_type_names.append("JsonArray")

            elif t is JsonValue:
                expected_type_names.append("JsonValue")

            elif isinstance(t, type) and issubclass(t, enum.IntEnum):
                expected_type_names.append(t.__name__)

            elif isinstance(t, type) and issubclass(t, StrEnum):
                expected_type_names.append(t.__name__)

            elif isinstance(t, type) and issubclass(t, JsonObjectConvertible):
                expected_type_names.append(t.__name__)

            else:
                expected_type_names.append(repr(t))

        return (
            False,
            None,
            GetIssueInfo(
                ctx.get_path(),
                JsonIssueCode.INVALID_TYPE,
                f"Expected one of {' | '.join(expected_type_names)}, got {type(value).__name__}",
                value,
            ),
        )

    expected_type: object = types[0]
    use_shallow_validation: bool = ctx.get_use_shallow_validation()

    if isinstance(expected_type, ArrayOf):
        try:
            if use_shallow_validation:
                _validate_json_array_shallow(ctx, value)
            else:
                validate_json_array(ctx, value)

        except JsonError as e:
            issue_code: JsonIssueCode = JsonIssueCode.INVALID_TYPE if e.get_path() == ctx.get_path() else JsonIssueCode.INVALID_VALUE
            issue_value: object = value if e.get_path() == ctx.get_path() else _MISSING_ISSUE_VALUE
            return False, None, GetIssueInfo(e.get_path(), issue_code, _get_exception_reason(e), issue_value, e)

        out: list[object] = []

        for i, item in enumerate(cast(JsonArray, value)):
            ok, result, error = _try_read_value_as_types(
                ctx.create_child(i),
                item,
                _normalize_type_or_types(expected_type.get_element_types())
            )

            if not ok:
                return False, None, error

            out.append(result)

        return True, out, None

    if isinstance(expected_type, ValuesOf):
        try:
            if use_shallow_validation:
                _validate_json_object_shallow(ctx, value)
            else:
                validate_json_object(ctx, value)

        except JsonError as e:
            issue_code: JsonIssueCode = JsonIssueCode.INVALID_TYPE if e.get_path() == ctx.get_path() else JsonIssueCode.INVALID_VALUE
            issue_value: object = value if e.get_path() == ctx.get_path() else _MISSING_ISSUE_VALUE
            return False, None, GetIssueInfo(e.get_path(), issue_code, _get_exception_reason(e), issue_value, e)

        out: dict[str, object] = {}

        for k, item in cast(JsonObject, value).items():
            ok, result, error = _try_read_value_as_types(
                ctx.create_child(k),
                item,
                _normalize_type_or_types(expected_type.get_value_types())
            )

            if not ok:
                return False, None, error

            out[k] = result

        return True, out, None

    if expected_type is str:
        if not isinstance(value, str):
            return False, None, GetIssueInfo(ctx.get_path(), JsonIssueCode.INVALID_TYPE, f"Expected string, got {type(value).__name__}", value)

        return True, value, None

    if expected_type is int:
        if not _is_strict_int(value):
            return False, None, GetIssueInfo(ctx.get_path(), JsonIssueCode.INVALID_TYPE, f"Expected integer, got {type(value).__name__}", value)

        return True, cast(int, value), None

    if expected_type is float:
        if _is_strict_int(value):
            try:
                return True, float(cast(int, value)), None

            except OverflowError as e:
                return False, None, GetIssueInfo(ctx.get_path(), JsonIssueCode.VALUE_CONVERSION_FAILED, "Integer too large to convert to float", value, e)

        if isinstance(value, float):
            if math.isfinite(value):
                return True, value, None

            return False, None, GetIssueInfo(ctx.get_path(), JsonIssueCode.INVALID_VALUE, "Non-finite float", value)

        return False, None, GetIssueInfo(ctx.get_path(), JsonIssueCode.INVALID_TYPE, f"Expected number, got {type(value).__name__}", value)

    if expected_type is bool:
        if not isinstance(value, bool):
            return False, None, GetIssueInfo(ctx.get_path(), JsonIssueCode.INVALID_TYPE, f"Expected boolean, got {type(value).__name__}", value)

        return True, value, None

    if expected_type is JsonPrimitive:
        try:
            if use_shallow_validation:
                _validate_json_primitive_shallow(ctx, value)
            else:
                validate_json_primitive(ctx, value)

        except JsonError as e:
            issue_code: JsonIssueCode = JsonIssueCode.INVALID_TYPE if e.get_path() == ctx.get_path() else JsonIssueCode.INVALID_VALUE
            issue_value: object = value if e.get_path() == ctx.get_path() else _MISSING_ISSUE_VALUE
            return False, None, GetIssueInfo(e.get_path(), issue_code, _get_exception_reason(e), issue_value, e)

        return True, cast(JsonPrimitive, value), None

    if expected_type is JsonObject:
        try:
            if use_shallow_validation:
                _validate_json_object_shallow(ctx, value)
            else:
                validate_json_object(ctx, value)

        except JsonError as e:
            issue_code: JsonIssueCode = JsonIssueCode.INVALID_TYPE if e.get_path() == ctx.get_path() else JsonIssueCode.INVALID_VALUE
            issue_value: object = value if e.get_path() == ctx.get_path() else _MISSING_ISSUE_VALUE
            return False, None, GetIssueInfo(e.get_path(), issue_code, _get_exception_reason(e), issue_value, e)

        return True, cast(JsonObject, value), None

    if expected_type is JsonArray:
        try:
            if use_shallow_validation:
                _validate_json_array_shallow(ctx, value)
            else:
                validate_json_array(ctx, value)

        except JsonError as e:
            issue_code: JsonIssueCode = JsonIssueCode.INVALID_TYPE if e.get_path() == ctx.get_path() else JsonIssueCode.INVALID_VALUE
            issue_value: object = value if e.get_path() == ctx.get_path() else _MISSING_ISSUE_VALUE
            return False, None, GetIssueInfo(e.get_path(), issue_code, _get_exception_reason(e), issue_value, e)

        return True, cast(JsonArray, value), None

    if expected_type is JsonValue:
        try:
            if use_shallow_validation:
                _validate_json_value_shallow(ctx, value)
            else:
                validate_json_value(ctx, value)

        except JsonError as e:
            issue_code: JsonIssueCode = JsonIssueCode.INVALID_TYPE if e.get_path() == ctx.get_path() else JsonIssueCode.INVALID_VALUE
            issue_value: object = value if e.get_path() == ctx.get_path() else _MISSING_ISSUE_VALUE
            return False, None, GetIssueInfo(e.get_path(), issue_code, _get_exception_reason(e), issue_value, e)

        return True, cast(JsonValue, value), None

    if isinstance(expected_type, type) and issubclass(expected_type, enum.IntEnum):
        if not _is_strict_int(value):
            issue_info: GetIssueInfo = GetIssueInfo(
                ctx.get_path(),
                JsonIssueCode.INVALID_TYPE,
                f"Expected integer for {expected_type.__name__}, got {type(value).__name__}",
                value,
            )
            return False, None, issue_info

        try:
            return True, expected_type(cast(int, value)), None
        except ValueError as e:
            issue_info = GetIssueInfo(
                ctx.get_path(),
                JsonIssueCode.INVALID_VALUE,
                f"Invalid {expected_type.__name__} value: {value!r}",
                value,
                e,
            )
            return False, None, issue_info

    if isinstance(expected_type, type) and issubclass(expected_type, StrEnum):
        if not isinstance(value, str):
            issue_info = GetIssueInfo(
                ctx.get_path(),
                JsonIssueCode.INVALID_TYPE,
                f"Expected string for {expected_type.__name__}, got {type(value).__name__}",
                value,
            )
            return False, None, issue_info

        try:
            return True, expected_type(value), None
        except ValueError as e:
            issue_info = GetIssueInfo(
                ctx.get_path(),
                JsonIssueCode.INVALID_VALUE,
                f"Invalid {expected_type.__name__} value: {value!r}",
                value,
                e,
            )
            return False, None, issue_info

    if isinstance(expected_type, type) and issubclass(expected_type, JsonObjectConvertible):
        try:
            if use_shallow_validation:
                _validate_json_object_shallow(ctx, value)
            else:
                validate_json_object(ctx, value)

        except JsonError as e:
            issue_code: JsonIssueCode = JsonIssueCode.INVALID_TYPE if e.get_path() == ctx.get_path() else JsonIssueCode.INVALID_VALUE
            issue_value: object = value if e.get_path() == ctx.get_path() else _MISSING_ISSUE_VALUE
            return False, None, GetIssueInfo(e.get_path(), issue_code, _get_exception_reason(e), issue_value, e)

        try:
            return True, expected_type.from_json_object(ctx, cast(JsonObject, value)), None

        except JsonError as e:
            issue_value = value if e.get_path() == ctx.get_path() else _MISSING_ISSUE_VALUE
            return False, None, GetIssueInfo(e.get_path(), JsonIssueCode.INVALID_VALUE, _get_exception_reason(e), issue_value, e)

        except (TypeError, ValueError) as e:
            return False, None, GetIssueInfo(
                ctx.get_path(),
                JsonIssueCode.DESERIALIZATION_FAILED,
                f"Failed to deserialize {expected_type.__name__}",
                value,
                e,
            )

    raise TypeError(f"Unsupported get type: {expected_type!r}")


def get(ctx: JsonContext, json_object: JsonObject, key: str, type_or_types: object, *, default: object = _MISSING_DEFAULT) -> object:
    child_ctx: JsonContext = ctx.create_child(key)
    types: tuple[object, ...] = _normalize_type_or_types(type_or_types)

    if not types:
        raise ValueError("type_or_types must not be empty")

    if key not in json_object:
        _record_get_issue(child_ctx, JsonIssueCode.MISSING_KEY, "Missing key")
        return _resolve_default_value(default, types)

    ok, result, error = _try_read_value_as_types(child_ctx, json_object[key], types)

    if ok:
        return result

    if error is None:
        raise AssertionError("Unreachable: typed read failed without error information")

    error_ctx: JsonContext = JsonContext(
        path=error.get_path(),
        max_depth=ctx.get_max_depth(),
        issues=ctx.get_issues(),
        max_issue_value_repr_length=ctx.get_max_issue_value_repr_length(),
        use_shallow_validation=ctx.get_use_shallow_validation()
    )

    _record_get_issue(
        error_ctx,
        error.get_code(),
        error.get_message(),
        value=error.get_value(),
        exc=error.get_exc(),
    )

    return _resolve_default_value(default, types)


def require(ctx: JsonContext, json_object: JsonObject, key: str, type_or_types: object) -> object:
    child_ctx: JsonContext = ctx.create_child(key)
    types: tuple[object, ...] = _normalize_type_or_types(type_or_types)

    if not types:
        raise ValueError("type_or_types must not be empty")

    if key not in json_object:
        raise JsonError("Missing key", child_ctx.get_path())

    ok, result, error = _try_read_value_as_types(child_ctx, json_object[key], types)

    if ok:
        return result

    if error is None:
        raise AssertionError("Unreachable: typed read failed without error information")

    exc: Optional[BaseException] = error.get_exc()

    if isinstance(exc, (TypeError, ValueError)):
        raise exc

    raise JsonError(error.get_message(), error.get_path())


def from_convertible(ctx: JsonContext, key: str, convertible: JsonObjectConvertible) -> JsonObject:
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
        TypeError: Raised when the produced value is not a valid JSON object,
            plus any ``TypeError`` raised directly by ``to_json_object()``.
        ValueError: Raised when ``to_json_object()`` fails with an invalid value.
    """
    child_ctx: JsonContext = ctx.create_child(key)

    json_object: JsonObject = convertible.to_json_object(child_ctx)

    try:
        validate_json_object(child_ctx, json_object)
    except JsonError as e:
        raise TypeError(f"Invalid JSON object produced by {type(convertible).__name__} for key {key!r}: {e}") from e

    return json_object


def from_convertibles(ctx: JsonContext, key: str, convertibles: Iterable[JsonObjectConvertible]) -> list[JsonObject]:
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
        TypeError: Raised when any produced value is not a valid JSON object,
            plus any ``TypeError`` raised directly by an element's ``to_json_object()``.
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
    "Factory",
    "get",
    "ArrayOf",
    "ValuesOf",
    "from_convertible",
    "from_convertibles",
    "append_json_value_path_part",
    "JsonContext",
    "JsonIssueSeverity",
    "JsonIssueCode",
    "JsonIssue",
    "StrEnum",
    "require",
]

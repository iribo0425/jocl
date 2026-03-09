# JOCL (JSON Object Conversion Lib)

A small Python utility library that makes it easier to convert Python class instances to and from JSON objects.

With this library, you can:
- convert class instances into JSON-compatible dictionaries
- rebuild class instances from JSON objects
- validate JSON values before saving or loading
- read and write JSON files safely
- locate errors inside nested JSON data more easily

## Examples

### Minimal Example

This example shows the basic conversion flow in both directions.
`to_json_object()` converts a class instance into a JSON object, and `from_json_object()` builds a class instance from a JSON object.
```python
from dataclasses import dataclass
from jocl import JsonObject, JsonObjectConvertible, JsonValueContext

@dataclass
class User(JsonObjectConvertible):
    name: str
    age: int

    def to_json_object(self, ctx: JsonValueContext) -> JsonObject:
        return {
            "name": self.name,
            "age": self.age,
        }

    @classmethod
    def from_json_object(cls, ctx: JsonValueContext, json_object: JsonObject) -> "User":
        return cls(
            name=json_object["name"],
            age=json_object["age"],
        )

ctx = JsonValueContext()
user = User(name="Alice", age=30)

json_object = user.to_json_object(ctx)
print(json_object)
# {'name': 'Alice', 'age': 30}

loaded_user = User.from_json_object(ctx, json_object)
print(loaded_user)
# User(name='Alice', age=30)
```

### Tolerant Deserialization

This example uses the `get_*` helpers to read values with defaults.
It is useful when missing or invalid values should fall back to safe default values instead of raising an error.
```python
from dataclasses import dataclass
from jocl import JsonObject, JsonObjectConvertible, JsonValueContext, get_bool, get_int, get_str

@dataclass
class UserSettings(JsonObjectConvertible):
    theme: str = "dark"
    max_item_count: int = 20
    show_tips: bool = True

    def to_json_object(self, ctx: JsonValueContext) -> JsonObject:
        return {
            "theme": self.theme,
            "max_item_count": self.max_item_count,
            "show_tips": self.show_tips,
        }

    @classmethod
    def from_json_object(cls, ctx: JsonValueContext, json_object: JsonObject) -> "UserSettings":
        return cls(
            theme=get_str(ctx, json_object, "theme", default="dark"),
            max_item_count=get_int(ctx, json_object, "max_item_count", default=20),
            show_tips=get_bool(ctx, json_object, "show_tips", default=True),
        )

ctx = JsonValueContext()
user_settings = UserSettings.from_json_object(ctx, {"theme": "light"})
print(user_settings)
# UserSettings(theme='light', max_item_count=20, show_tips=True)
```

### Strict Deserialization

This example uses the `require_*` helpers to read required values.
It is useful when input data must have the expected fields and types, and invalid input should immediately raise an error.
```python
from dataclasses import dataclass
from jocl import JsonObject, JsonObjectConvertible, JsonValueContext, require_bool, require_int, require_str

@dataclass
class User(JsonObjectConvertible):
    name: str
    age: int
    active: bool

    def to_json_object(self, ctx: JsonValueContext) -> JsonObject:
        return {
            "name": self.name,
            "age": self.age,
            "active": self.active,
        }

    @classmethod
    def from_json_object(cls, ctx: JsonValueContext, json_object: JsonObject) -> "User":
        return cls(
            name=require_str(ctx, json_object, "name"),
            age=require_int(ctx, json_object, "age"),
            active=require_bool(ctx, json_object, "active"),
        )

ctx = JsonValueContext()
user = User.from_json_object(ctx, {"name": "Alice", "age": 30, "active": True})
print(user)
# User(name='Alice', age=30, active=True)
```

### Nested Objects and Lists

This example shows how to deserialize nested objects and lists of objects.
It is useful when one class contains other `JsonObjectConvertible` objects, such as an address object or a list of tags.
```python
from dataclasses import dataclass, field
from jocl import (
    JsonObject,
    JsonObjectConvertible,
    JsonValueContext,
    convert_convertibles_to_json_objects,
    get_convertible,
    get_convertibles,
    get_str,
)

@dataclass
class Address(JsonObjectConvertible):
    city: str = ""
    country: str = ""

    def to_json_object(self, ctx: JsonValueContext) -> JsonObject:
        return {
            "city": self.city,
            "country": self.country,
        }

    @classmethod
    def from_json_object(cls, ctx: JsonValueContext, json_object: JsonObject) -> "Address":
        return cls(
            city=get_str(ctx, json_object, "city", default=""),
            country=get_str(ctx, json_object, "country", default=""),
        )

@dataclass
class Tag(JsonObjectConvertible):
    name: str = ""

    def to_json_object(self, ctx: JsonValueContext) -> JsonObject:
        return {
            "name": self.name,
        }

    @classmethod
    def from_json_object(cls, ctx: JsonValueContext, json_object: JsonObject) -> "Tag":
        return cls(
            name=get_str(ctx, json_object, "name", default=""),
        )

@dataclass
class User(JsonObjectConvertible):
    name: str = ""
    address: Address = field(default_factory=Address)
    tags: list[Tag] = field(default_factory=list)

    def to_json_object(self, ctx: JsonValueContext) -> JsonObject:
        return {
            "name": self.name,
            "address": self.address.to_json_object(ctx.create_child("address")),
            "tags": convert_convertibles_to_json_objects(ctx.create_child("tags"), self.tags),
        }

    @classmethod
    def from_json_object(cls, ctx: JsonValueContext, json_object: JsonObject) -> "User":
        return cls(
            name=get_str(ctx, json_object, "name", default=""),
            address=get_convertible(ctx, json_object, "address", Address, Address),
            tags=get_convertibles(ctx, json_object, "tags", Tag),
        )

ctx = JsonValueContext()
user = User(
    name="Alice",
    address=Address(city="Tokyo", country="Japan"),
    tags=[Tag(name="admin"), Tag(name="developer")],
)

json_object = user.to_json_object(ctx)
print(json_object)
# {
#     'name': 'Alice',
#     'address': {'city': 'Tokyo', 'country': 'Japan'},
#     'tags': [{'name': 'admin'}, {'name': 'developer'}],
# }

loaded_user = User.from_json_object(ctx, json_object)
print(loaded_user)
# User(
#     name='Alice',
#     address=Address(city='Tokyo', country='Japan'),
#     tags=[Tag(name='admin'), Tag(name='developer')],
# )
```

## Installation

Copy `jocl.py` into your project and import what you need.

```python
from jocl import JsonObject, JsonObjectConvertible
```

## Requirements

- Python 3.9.7+

## License

This project is licensed under the MIT License.
See the `LICENSE` file for details.

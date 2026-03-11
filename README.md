# JOCL (JSON Object Conversion Lib)

A small utility library for converting Python class instances to and from JSON objects.

With this library, you can:
- convert class instances into JSON objects
- reconstruct class instances from JSON objects
- validate JSON values before saving or loading
- read and write JSON files safely
- locate errors in nested JSON data more easily

## Examples

### Basic Usage

This example shows the basic workflow: convert an instance to a JSON object, write it to a JSON file, and load it back into a class instance.
It uses the `get_*` helpers during deserialization to return default values when fields are missing or invalid.

```python
from dataclasses import dataclass
from pathlib import Path
from jocl import (
    JsonContext,
    JsonObject,
    JsonObjectConvertible,
    dump_convertible,
    get_int,
    get_str,
    load_convertible,
)


@dataclass
class User(JsonObjectConvertible):
    name: str = ""
    age: int = 0

    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        return {
            "name": self.name,
            "age": self.age,
        }

    @classmethod
    def from_json_object(cls, ctx: JsonContext, json_object: JsonObject) -> "User":
        return cls(
            name=get_str(ctx, json_object, "name", default=""),
            age=get_int(ctx, json_object, "age", default=0),
        )

    @classmethod
    def create_default(cls) -> "User":
        return cls()


ctx = JsonContext()
user = User(name="Alice", age=30)
path = Path("user.json")

# Convert the instance to a JSON object.
json_object = user.to_json_object(ctx)
print(json_object)
# {'name': 'Alice', 'age': 30}

# Write the instance to a JSON file.
dump_convertible(ctx, user, path)

# Load the instance back from the JSON file.
loaded_user = load_convertible(ctx, User, path)
print(loaded_user)
# User(name='Alice', age=30)
```

For strict validation, use the following version of `from_json_object()`:

```python
from jocl import require_int, require_str

@classmethod
def from_json_object(cls, ctx: JsonContext, json_object: JsonObject) -> "User":
    return cls(
        name=require_str(ctx, json_object, "name"),
        age=require_int(ctx, json_object, "age"),
    )
```

### Nested Objects and Lists

This example shows how to deserialize nested objects and lists of objects.
It is useful when a class contains other `JsonObjectConvertible` objects, such as an address object or a list of tags.

```python
from dataclasses import dataclass, field
from jocl import (
    JsonContext,
    JsonObject,
    JsonObjectConvertible,
    convert_convertible_to_json_object,
    convert_convertibles_to_json_objects,
    get_convertible,
    get_convertibles,
    get_str,
)

@dataclass
class Address(JsonObjectConvertible):
    city: str = ""
    country: str = ""

    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        return {
            "city": self.city,
            "country": self.country,
        }

    @classmethod
    def from_json_object(cls, ctx: JsonContext, json_object: JsonObject) -> "Address":
        return cls(
            city=get_str(ctx, json_object, "city", default=""),
            country=get_str(ctx, json_object, "country", default=""),
        )

    @classmethod
    def create_default(cls) -> "Address":
        return cls()

@dataclass
class Tag(JsonObjectConvertible):
    name: str = ""

    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        return {
            "name": self.name,
        }

    @classmethod
    def from_json_object(cls, ctx: JsonContext, json_object: JsonObject) -> "Tag":
        return cls(
            name=get_str(ctx, json_object, "name", default=""),
        )

    @classmethod
    def create_default(cls) -> "Tag":
        return cls()

@dataclass
class User(JsonObjectConvertible):
    name: str = ""
    address: Address = field(default_factory=Address.create_default)
    tags: list[Tag] = field(default_factory=list)

    def to_json_object(self, ctx: JsonContext) -> JsonObject:
        return {
            "name": self.name,
            "address": convert_convertible_to_json_object(ctx, "address", self.address),
            "tags": convert_convertibles_to_json_objects(ctx, "tags", self.tags),
        }

    @classmethod
    def from_json_object(cls, ctx: JsonContext, json_object: JsonObject) -> "User":
        return cls(
            name=get_str(ctx, json_object, "name", default=""),
            address=get_convertible(ctx, json_object, "address", Address),
            tags=get_convertibles(ctx, json_object, "tags", Tag),
        )

    @classmethod
    def create_default(cls) -> "User":
        return cls()

ctx = JsonContext()
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

### Collecting Issues

This example shows how the `get_*` helpers collect non-fatal issues in `JsonContext`.
After reading the JSON object, you can inspect the collected issues and print them.

```python
from jocl import JsonContext, JsonObject, get_int, get_str

json_object: JsonObject = {
    "name": 123,
    # "age" is missing
}

ctx = JsonContext()

name = get_str(ctx, json_object, "name", default="default name")
age = get_int(ctx, json_object, "age", default=456)

print(name)
print(age)

for issue in ctx.get_issues():
    print(issue)

# default name
# 456
# JSON issue at /name: Expected string, got int; severity=WARNING; code=INVALID_TYPE; value_type=int; value=123
# JSON issue at /age: Missing key; severity=WARNING; code=MISSING_KEY
```

## Installation

Copy `jocl.py` into your project and import what you need.

```python
from jocl import JsonObject, JsonObjectConvertible
```

## Requirements

- Python 3.9+
- No third-party dependencies

## License

This project is licensed under the MIT License.
See the `LICENSE` file for details.

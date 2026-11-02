import pytest
from pydantic import ValidationError
from sales_manager_api.product_models import ProductCreate, ProductPatch

VALID = {"code": "COFFEE", "name": "コーヒー", "default_unit_price_yen": 550}


@pytest.mark.parametrize("price", [0, 9_999_999])
def test_price_boundaries(price):
    assert (
        ProductCreate(
            **{**VALID, "default_unit_price_yen": price}
        ).default_unit_price_yen
        == price
    )


@pytest.mark.parametrize("price", [-1, 10_000_000, True, 550.0, "550", None])
def test_price_rejects_invalid_types_and_bounds(price):
    for model, data in [
        (ProductCreate, {**VALID, "default_unit_price_yen": price}),
        (ProductPatch, {"default_unit_price_yen": price}),
    ]:
        with pytest.raises(ValidationError):
            model(**data)


@pytest.mark.parametrize("code", ["", "coffee", "_CODE", "A B", "A" * 33, "A\n", 123])
def test_invalid_product_code(code):
    with pytest.raises(ValidationError):
        ProductCreate(**{**VALID, "code": code})


@pytest.mark.parametrize("name", ["", " \t\n", "　", "あ" * 101, True])
def test_invalid_name(name):
    for model, data in [
        (ProductCreate, {**VALID, "name": name}),
        (ProductPatch, {"name": name}),
    ]:
        with pytest.raises(ValidationError):
            model(**data)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"is_active": None},
        {"code": "OTHER"},
        {"is_active": "false"},
        {"is_active": 0},
        {"version": 2},
    ],
)
def test_patch_rejects_empty_null_immutable_or_coerced_fields(body):
    with pytest.raises(ValidationError):
        ProductPatch(**body)


def test_partial_patch_preserves_unset_and_valid_unicode_name():
    assert ProductPatch(is_active=False).model_dump(exclude_unset=True) == {
        "is_active": False
    }
    assert (
        ProductCreate(**{**VALID, "name": "𠮷" * 100, "code": "A" * 32}).name
        == "𠮷" * 100
    )
    with pytest.raises(ValidationError):
        ProductCreate(**VALID, actor="spoofed")

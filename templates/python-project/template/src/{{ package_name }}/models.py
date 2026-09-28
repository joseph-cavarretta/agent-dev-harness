from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Base for data contracts: strict types, no unknown fields, immutable."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

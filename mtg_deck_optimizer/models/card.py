"""
Card data models representing Magic: The Gathering cards from Scryfall metadata.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, computed_field


class CardPrices(BaseModel):
    usd: Optional[float] = Field(default=None, description="Price in regular USD")
    usd_foil: Optional[float] = Field(default=None, description="Price in foil USD")
    usd_etched: Optional[float] = Field(default=None, description="Price in etched foil USD")
    eur: Optional[float] = Field(default=None, description="Price in EUR")
    eur_foil: Optional[float] = Field(default=None, description="Price in foil EUR")
    tix: Optional[float] = Field(default=None, description="Price in MTGO Tix")

    @classmethod
    def from_scryfall(cls, prices_dict: Optional[Dict[str, Any]]) -> "CardPrices":
        if not prices_dict:
            return cls()

        def _to_float(val: Any) -> Optional[float]:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        return cls(
            usd=_to_float(prices_dict.get("usd")),
            usd_foil=_to_float(prices_dict.get("usd_foil")),
            usd_etched=_to_float(prices_dict.get("usd_etched")),
            eur=_to_float(prices_dict.get("eur")),
            eur_foil=_to_float(prices_dict.get("eur_foil")),
            tix=_to_float(prices_dict.get("tix")),
        )


class CardImageUris(BaseModel):
    small: Optional[str] = None
    normal: Optional[str] = None
    large: Optional[str] = None
    png: Optional[str] = None
    art_crop: Optional[str] = None
    border_crop: Optional[str] = None


class CardFace(BaseModel):
    name: str
    mana_cost: Optional[str] = None
    type_line: Optional[str] = None
    oracle_text: Optional[str] = None
    colors: List[str] = Field(default_factory=list)
    power: Optional[str] = None
    toughness: Optional[str] = None
    loyalty: Optional[str] = None
    image_uris: Optional[CardImageUris] = None


class Card(BaseModel):
    id: str = Field(description="Scryfall UUID for the card printing")
    oracle_id: Optional[str] = Field(default=None, description="Scryfall Oracle ID")
    name: str = Field(description="Full card name (e.g., 'Sol Ring', 'Fire // Ice')")
    mana_cost: Optional[str] = Field(default=None, description="Mana cost string, e.g. '{2}{U}{U}'")
    cmc: float = Field(default=0.0, description="Converted Mana Cost / Mana Value")
    type_line: str = Field(default="", description="Full type line, e.g. 'Legendary Creature — Human Wizard'")
    oracle_text: Optional[str] = Field(default=None, description="Rules text for the card")
    colors: List[str] = Field(default_factory=list, description="Card colors, e.g. ['W', 'U']")
    color_identity: List[str] = Field(default_factory=list, description="Commander color identity, e.g. ['W', 'U', 'B']")
    keywords: List[str] = Field(default_factory=list, description="Card keywords, e.g. ['Flying', 'Haste']")
    set_code: Optional[str] = Field(default=None, description="Set code in lowercase, e.g. 'lea', 'cmm'")
    collector_number: Optional[str] = Field(default=None, description="Collector number in set")
    rarity: Optional[str] = Field(default=None, description="Rarity: common, uncommon, rare, mythic, special")
    layout: Optional[str] = Field(default="normal", description="Card layout: normal, transform, modal_dfc, etc.")
    power: Optional[str] = None
    toughness: Optional[str] = None
    loyalty: Optional[str] = None
    card_faces: Optional[List[CardFace]] = Field(default=None, description="Faces for multi-faced cards")
    image_uris: Optional[CardImageUris] = None
    prices: CardPrices = Field(default_factory=CardPrices)
    legalities: Dict[str, str] = Field(default_factory=dict, description="Format legalities")
    scryfall_uri: Optional[str] = None

    @computed_field
    @property
    def price_usd(self) -> Optional[float]:
        """Convenience property to access normal USD price directly."""
        if self.prices and self.prices.usd is not None:
            return self.prices.usd
        return None

    @computed_field
    @property
    def primary_type(self) -> str:
        """Determines the primary card type (Creature, Instant, Sorcery, Artifact, Enchantment, Land, Planeswalker, Battle, etc.)."""
        tl = self.type_line.split("—")[0].strip() if "—" in self.type_line else self.type_line
        types_priority = [
            "Creature",
            "Planeswalker",
            "Battle",
            "Instant",
            "Sorcery",
            "Artifact",
            "Enchantment",
            "Land",
        ]
        for t in types_priority:
            if t in tl:
                return t
        return "Other"

    @computed_field
    @property
    def is_commander_eligible(self) -> bool:
        """Returns True if the card can normally be a Commander."""
        if "Legendary" in self.type_line and "Creature" in self.type_line:
            return True
        if "can be your commander" in (self.oracle_text or "").lower():
            return True
        # Check faces for modal DFC or Transform legends
        if self.card_faces:
            front = self.card_faces[0]
            if "Legendary" in (front.type_line or "") and "Creature" in (front.type_line or ""):
                return True
            if "can be your commander" in (front.oracle_text or "").lower():
                return True
        return False

    @classmethod
    def from_scryfall_dict(cls, data: Dict[str, Any]) -> "Card":
        """Builds a Card instance from Scryfall API JSON response."""
        # Multi-faced cards handling (DFCs, MDFCs, Transforms)
        faces_data = data.get("card_faces")
        faces: Optional[List[CardFace]] = None
        mana_cost = data.get("mana_cost")
        oracle_text = data.get("oracle_text")
        type_line = data.get("type_line", "")
        img_dict = data.get("image_uris")

        if faces_data and isinstance(faces_data, list):
            faces = []
            for f in faces_data:
                f_imgs = f.get("image_uris")
                faces.append(
                    CardFace(
                        name=f.get("name", ""),
                        mana_cost=f.get("mana_cost"),
                        type_line=f.get("type_line"),
                        oracle_text=f.get("oracle_text"),
                        colors=f.get("colors", []),
                        power=f.get("power"),
                        toughness=f.get("toughness"),
                        loyalty=f.get("loyalty"),
                        image_uris=CardImageUris(**f_imgs) if f_imgs else None,
                    )
                )
            # If top-level type_line, mana_cost, or oracle_text is missing, aggregate from faces
            if not type_line and faces:
                type_line = " // ".join(f.type_line for f in faces if f.type_line)
            if not mana_cost and faces:
                mana_cost = faces[0].mana_cost
            if not oracle_text and faces:
                oracle_text = "\n//\n".join(f.oracle_text for f in faces if f.oracle_text)
            if not img_dict and faces and faces[0].image_uris:
                img_dict = faces[0].image_uris.model_dump()

        images = CardImageUris(**img_dict) if img_dict else None
        prices = CardPrices.from_scryfall(data.get("prices"))

        # Aggregate colors from faces if missing at top level
        colors = data.get("colors")
        if not colors and faces:
            colors = []
            for f in faces:
                for c in (f.colors or []):
                    if c not in colors:
                        colors.append(c)

        return cls(
            id=data["id"],
            oracle_id=data.get("oracle_id"),
            name=data["name"],
            mana_cost=mana_cost,
            cmc=float(data.get("cmc", 0.0)),
            type_line=type_line,
            oracle_text=oracle_text,
            colors=data.get("colors", []),
            color_identity=data.get("color_identity", []),
            keywords=data.get("keywords", []),
            set_code=data.get("set"),
            collector_number=data.get("collector_number"),
            rarity=data.get("rarity"),
            layout=data.get("layout", "normal"),
            power=data.get("power"),
            toughness=data.get("toughness"),
            loyalty=data.get("loyalty"),
            card_faces=faces,
            image_uris=images,
            prices=prices,
            legalities=data.get("legalities", {}),
            scryfall_uri=data.get("scryfall_uri"),
        )

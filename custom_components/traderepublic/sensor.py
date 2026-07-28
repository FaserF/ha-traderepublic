"""Sensor platform for Trade Republic integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TradeRepublicDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Trade Republic sensor entities based on a config entry."""
    coordinator: TradeRepublicDataUpdateCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    entities: list[SensorEntity] = [
        TradeRepublicNetWorthSensor(coordinator),
        TradeRepublicCashSensor(coordinator),
        TradeRepublicInvestedSensor(coordinator),
        TradeRepublicTotalProfitSensor(coordinator),
        TradeRepublicTotalProfitPercentSensor(coordinator),
        TradeRepublicExemptionTotalSensor(coordinator),
        TradeRepublicExemptionUsedSensor(coordinator),
        TradeRepublicSavingsPlansCountSensor(coordinator),
    ]

    async_add_entities(entities)


class TradeRepublicBaseEntity(
    CoordinatorEntity[TradeRepublicDataUpdateCoordinator], SensorEntity
):
    """Base class for all Trade Republic entities sharing device registration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TradeRepublicDataUpdateCoordinator,
        entry_id: str | None = None,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        if entry_id is None:
            entry_id = (
                coordinator.config_entry.entry_id if coordinator.config_entry else ""
            )
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Trade Republic Portfolio",
            manufacturer="Trade Republic Bank GmbH",
            model="Trade Republic Mobile App Interface",
            configuration_url="https://app.traderepublic.com",
        )


class TradeRepublicNetWorthSensor(TradeRepublicBaseEntity):
    """Sensor for Trade Republic Total Portfolio Net Value."""

    _attr_translation_key = "net_value"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, coordinator: TradeRepublicDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"traderepublic_net_value_{self._entry_id}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("net_value")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes of the sensor."""
        if not self.coordinator.data:
            return None
        return {
            "holdings": self.coordinator.data.get("holdings", []),
            "invested_capital": self.coordinator.data.get("invested_capital", 0.0),
            "total_profit": self.coordinator.data.get("total_profit", 0.0),
            "total_profit_percent": self.coordinator.data.get(
                "total_profit_percent", 0.0
            ),
            "savings_plans_count": self.coordinator.data.get("savings_plans_count", 0),
            "exemption_total": self.coordinator.data.get("exemption_total", 1000.00),
            "exemption_used": self.coordinator.data.get("exemption_used", 0.00),
            "recent_transactions": self.coordinator.data.get("recent_transactions", []),
        }


class TradeRepublicCashSensor(TradeRepublicBaseEntity):
    """Sensor for Trade Republic Available Cash Balance."""

    _attr_translation_key = "available_cash"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"

    def __init__(self, coordinator: TradeRepublicDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"traderepublic_available_cash_{self._entry_id}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("available_cash")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes of the sensor."""
        if not self.coordinator.data:
            return None
        return {
            "interest_rate": self.coordinator.data.get("interest_rate", 0.0375),
            "accrued_interest_daily": self.coordinator.data.get(
                "accrued_interest_daily", 0.0
            ),
            "accrued_interest_monthly_est": self.coordinator.data.get(
                "accrued_interest_monthly_est", 0.0
            ),
            "card_status": self.coordinator.data.get("card_status", "INACTIVE"),
            "card_saveback_earned": self.coordinator.data.get(
                "card_saveback_earned", 0.0
            ),
            "card_saveback_limit": self.coordinator.data.get(
                "card_saveback_limit", 0.0
            ),
        }


class TradeRepublicInvestedSensor(TradeRepublicBaseEntity):
    """Sensor for Trade Republic Invested Capital."""

    _attr_translation_key = "invested_capital"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TradeRepublicDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"traderepublic_invested_capital_{self._entry_id}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("invested_capital")


class TradeRepublicTotalProfitSensor(TradeRepublicBaseEntity):
    """Sensor for Trade Republic Total Profit/Loss."""

    _attr_translation_key = "total_profit"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TradeRepublicDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"traderepublic_total_profit_{self._entry_id}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("total_profit")


class TradeRepublicTotalProfitPercentSensor(TradeRepublicBaseEntity):
    """Sensor for Trade Republic Total Profit/Loss in Percent."""

    _attr_translation_key = "total_profit_percent"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TradeRepublicDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"traderepublic_total_profit_percent_{self._entry_id}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("total_profit_percent")


class TradeRepublicExemptionTotalSensor(TradeRepublicBaseEntity):
    """Sensor for Trade Republic Exemption Order Total Limit."""

    _attr_translation_key = "exemption_total"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TradeRepublicDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"traderepublic_exemption_total_{self._entry_id}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("exemption_total")


class TradeRepublicExemptionUsedSensor(TradeRepublicBaseEntity):
    """Sensor for Trade Republic Exemption Order Used Amount."""

    _attr_translation_key = "exemption_used"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "EUR"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TradeRepublicDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"traderepublic_exemption_used_{self._entry_id}"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("exemption_used")


class TradeRepublicSavingsPlansCountSensor(TradeRepublicBaseEntity):
    """Sensor for Trade Republic active savings plans count."""

    _attr_translation_key = "savings_plans_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "plans"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TradeRepublicDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"traderepublic_savings_plans_count_{self._entry_id}"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("savings_plans_count")

"""Primary-source providers for scheduled future catalysts."""

from .cme_fedwatch import CmeFedWatchProvider
from .geopolitical_news import GeopoliticalFeedProvider
from .official_calendars import (
    BeaCalendarProvider,
    BlsCalendarProvider,
    FederalReserveCalendarProvider,
    TreasuryAuctionProvider,
)
from .official_regulation import (
    CftcCalendarProvider,
    HouseCalendarProvider,
    OfficialRegulatoryFeedProvider,
    SenateCalendarProvider,
)

__all__ = [
    "BeaCalendarProvider",
    "BlsCalendarProvider",
    "CftcCalendarProvider",
    "CmeFedWatchProvider",
    "FederalReserveCalendarProvider",
    "GeopoliticalFeedProvider",
    "HouseCalendarProvider",
    "OfficialRegulatoryFeedProvider",
    "SenateCalendarProvider",
    "TreasuryAuctionProvider",
]

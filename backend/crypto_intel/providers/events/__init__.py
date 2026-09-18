"""Primary-source providers for scheduled future catalysts."""

from .central_banks import BojCalendarProvider, EcbCalendarProvider
from .cme_fedwatch import CmeFedWatchProvider
from .geopolitical_news import GeopoliticalFeedProvider
from .official_calendars import (
    BeaCalendarProvider,
    BlsCalendarProvider,
    FederalReserveCalendarProvider,
    TreasuryAuctionProvider,
)
from .official_congress import CongressBillActionProvider
from .official_protocols import EthereumProtocolProvider, SolanaProtocolProvider
from .official_regulation import (
    CftcCalendarProvider,
    HouseCalendarProvider,
    OfficialRegulatoryFeedProvider,
    SenateCalendarProvider,
)

__all__ = [
    "BeaCalendarProvider",
    "BlsCalendarProvider",
    "BojCalendarProvider",
    "CftcCalendarProvider",
    "CmeFedWatchProvider",
    "CongressBillActionProvider",
    "EcbCalendarProvider",
    "EthereumProtocolProvider",
    "FederalReserveCalendarProvider",
    "GeopoliticalFeedProvider",
    "HouseCalendarProvider",
    "OfficialRegulatoryFeedProvider",
    "SenateCalendarProvider",
    "SolanaProtocolProvider",
    "TreasuryAuctionProvider",
]

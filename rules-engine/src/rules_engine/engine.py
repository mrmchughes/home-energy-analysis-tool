from __future__ import annotations

import statistics as sts
from datetime import date
from typing import Any, List, Optional, Tuple

import numpy as np

from rules_engine.pydantic_models import (
    AnalysisType,
    BalancePointGraph,
    DhwInput,
    FuelType,
    NaturalGasBillingInput,
    NormalizedBillingPeriodRecordInput,
    OilPropaneBillingInput,
    SummaryInput,
    SummaryOutput,
    TemperatureInput,
)


def get_outputs_oil_propane(
    summary_input: SummaryInput,
    dhw_input: Optional[DhwInput],
    temperature_input: TemperatureInput,
    oil_propane_billing_input: OilPropaneBillingInput,
) -> Tuple[SummaryOutput, BalancePointGraph]:
    # TODO: normalize oil & propane to billing periods
    billing_periods = NotImplementedError()

    return get_outputs_normalized(
        summary_input, dhw_input, temperature_input, billing_periods
    )


def get_outputs_natural_gas(
    summary_input: SummaryInput,
    dhw_input: Optional[DhwInput],
    temperature_input: TemperatureInput,
    natural_gas_billing_input: NaturalGasBillingInput,
) -> Tuple[SummaryOutput, BalancePointGraph]:
    # TODO: normalize natural gas to billing periods
    billing_periods = NotImplementedError()

    return get_outputs_normalized(
        summary_input, dhw_input, temperature_input, billing_periods
    )


def get_outputs_normalized(
    summary_input: SummaryInput,
    dhw_input: Optional[DhwInput],
    temperature_input: TemperatureInput,
    billing_periods: List[NormalizedBillingPeriodRecordInput],
) -> Tuple[SummaryOutput, BalancePointGraph]:
    # Build a list of lists of temperatures, where each list of temperatures contains all the temperatures
    # in the corresponding billing period
    intermediate_billing_periods = []
    initial_balance_point = 60

    for billing_period in billing_periods:
        temperatures = []
        for i, d in enumerate(temperature_input.dates):
            # the HEAT Excel sheet is inclusive of the temperatures that fall on both the start and end dates
            if billing_period.period_start_date <= d <= billing_period.period_end_date:
                temperatures.append(temperature_input[i])

        analysis_type = date_to_analysis_type(billing_period.period_end_date)
        if billing_period.inclusion_override:
            analysis_type = billing_period.inclusion_override

        intermediate_billing_period = BillingPeriod(
            avg_temps=temperatures,
            usage=billing_period.usage,
            balance_point=initial_balance_point,
            analysis_type=analysis_type
        )
        intermediate_billing_periods.append(intermediate_billing_period)

    home = Home(
        summary_input=summary_input,
        billing_periods=intermediate_billing_periods,
        initial_balance_point=initial_balance_point,
        has_boiler_for_dhw=dhw_input is not None,
        same_fuel_dhw_heating=dhw_input is not None,
    )
    # home.calculate()
    # return (home.summaryOutput, home.balancePointGraph)

    raise NotImplementedError


def date_to_analysis_type(d: date) -> AnalysisType:
    months = {
        1: AnalysisType.INCLUDE,
        2: AnalysisType.INCLUDE,
        3: AnalysisType.INCLUDE,
        4: AnalysisType.DO_NOT_INCLUDE,
        5: AnalysisType.DO_NOT_INCLUDE,
        6: AnalysisType.DO_NOT_INCLUDE,
        7: AnalysisType.INCLUDE_IN_OTHER_ANALYSIS,
        8: AnalysisType.INCLUDE_IN_OTHER_ANALYSIS,
        9: AnalysisType.INCLUDE_IN_OTHER_ANALYSIS,
        10: AnalysisType.DO_NOT_INCLUDE,
        11: AnalysisType.DO_NOT_INCLUDE,
        12: AnalysisType.INCLUDE,
    }

    # TODO: finish implementation and unit test
    raise NotImplementedError


def hdd(avg_temp: float, balance_point: float) -> float:
    """
    Calculate the heating degree days on a given day for a given
    home.

    Args:
        avg_temp: average outdoor temperature on a given day
        balance_point: outdoor temperature (F) above which no heating
        is required in a given home
    """
    return max(0, balance_point - avg_temp)


def period_hdd(avg_temps: List[float], balance_point: float) -> float:
    """
    Sum up total heating degree days in a given time period for a given
    home.

    Args:
        avg_temps: list of daily average outdoor temperatures (F) for
        the period
        balance_point: outdoor temperature (F) above which no heating is
        required in a given home
    """
    return sum([hdd(temp, balance_point) for temp in avg_temps])


def average_indoor_temp(
    tstat_set: float, tstat_setback: float, setback_daily_hrs: float
) -> float:
    """
    Calculates the average indoor temperature.

    Args:
        tstat_set: the temp in F at which the home is normally set
        tstat_setback: temp in F at which the home is set during off
        hours
        setback_daily_hrs: average # of hours per day the home is at
        setback temp
    """
    # again, not sure if we should check for valid values here or whether we can
    # assume those kinds of checks will be handled at the point of user entry
    return (
        (24 - setback_daily_hrs) * tstat_set + setback_daily_hrs * tstat_setback
    ) / 24


def average_heat_load(
    design_set_point: float,
    avg_indoor_temp: float,
    balance_point: float,
    design_temp: float,
    ua: float,
) -> float:
    """
    Calculate the average heat load.

    Args:
        design_set_point: a standard internal temperature / thermostat
        set point - different from the preferred set point of an
        individual homeowner
        avg_indoor_temp: average indoor temperature on a given day
        balance_point: outdoor temperature (F) above which no heating
        is required
        design_temp: an outside temperature that represents one of the
        coldest days of the year for the given location of a home
        ua: the heat transfer coefficient
    """
    return (design_set_point - (avg_indoor_temp - balance_point) - design_temp) * ua


def max_heat_load(design_set_point: float, design_temp: float, ua: float) -> float:
    """
    Calculate the max heat load.

    Args:
        design_set_point: a standard internal temperature / thermostat
        set point - different from the preferred set point of an
        individual homeowner
        design_temp: an outside temperature that represents one of the
        coldest days of the year for the given location of a home
        ua: the heat transfer coefficient
    """
    return (design_set_point - design_temp) * ua


class Home:
    """
    Defines attributes and methods for calculating home heat metrics.

    The information associated with the energy usage of a single home owner
    is used to instantiate this class.  Using that information and the type
    of fuel used, calculates the UA for different billing periods and the
    standard deviation of the UA values across them.
    """

    def __init__(
        self,
        summary_input: SummaryInput,
        billing_periods: List[BillingPeriod],
        initial_balance_point: float = 60,
        has_boiler_for_dhw: bool = False,
        same_fuel_dhw_heating: bool = False,
    ):
        self.fuel_type = summary_input.fuel_type
        self.heat_sys_efficiency = summary_input.heating_system_efficiency
        self.thermostat_set_point = summary_input.thermostat_set_point
        self.balance_point = initial_balance_point
        self.has_boiler_for_dhw = has_boiler_for_dhw
        self.same_fuel_dhw_heating = same_fuel_dhw_heating
        self._initialize_billing_periods(billing_periods)

    def _initialize_billing_periods(
        self, billing_periods: List[BillingPeriod]
    ) -> None:
        """
        TODO
        """
        self.bills_winter = []
        self.bills_summer = []
        self.bills_shoulder = []

        # winter months 1; summer months -1; shoulder months 0
        for billing_period in billing_periods:
            if billing_period.analysis_type == AnalysisType.INCLUDE:
                self.bills_winter.append(billing_period)
            elif billing_period.analysis_type == AnalysisType.DO_NOT_INCLUDE:
                self.bills_summer.append(billing_period)
            else:
                self.bills_shoulder.append(billing_period)

        self._calculate_avg_summer_usage()
        self._calculate_avg_non_heating_usage()
        for billing_period in self.bills_winter:
            self.initialize_ua(billing_period)

    def _initialize_billing_periods_reworked(
        self, billingperiods: NaturalGasBillingInput
    ) -> None:
        """
        TODO
        """
        # assume for now that temps and usages have the same number of elements

        self.bills_winter = []
        self.bills_summer = []
        self.bills_shoulder = []

        # ngb_start_date = billingperiods.period_start_date
        # ngbs = billingperiods.records

        # TODO: fix these
        usages: List[float] = []
        inclusion_codes: List[int] = []
        temps: List[List[float]] = []

        # winter months 1; summer months -1; shoulder months 0
        for i, usage in enumerate(usages):
            billing_period = BillingPeriod(
                avg_temps=temps[i],
                usage=usage,
                balance_point=self.balance_point,
                inclusion_code=inclusion_codes[i],
            )

            if inclusion_codes[i] == 1:
                self.bills_winter.append(billing_period)
            elif inclusion_codes[i] == -1:
                self.bills_summer.append(billing_period)
            else:
                self.bills_shoulder.append(billing_period)

        self._calculate_avg_summer_usage()
        self._calculate_avg_non_heating_usage()
        for billing_period in self.bills_winter:
            self.initialize_ua(billing_period)

    def _calculate_avg_summer_usage(self) -> None:
        """
        Calculate average daily summer usage
        """
        summer_usage_total = sum([bp.usage for bp in self.bills_summer])
        summer_days = sum([bp.days for bp in self.bills_summer])
        if summer_days != 0:
            self.avg_summer_usage = summer_usage_total / summer_days
        else:
            self.avg_summer_usage = 0

    def _calculate_boiler_usage(self, fuel_multiplier: float) -> float:
        """
        Calculate boiler usage with oil or propane
        Args:
            fuel_multiplier: a constant that's determined by the fuel
            type
        """

        # self.num_occupants: the number of occupants in Home
        # self.water_heat_efficiency: a number indicating how efficient the heating system is

        return 0 * fuel_multiplier

    """
    your pseudocode looks correct provided there's outer logic that 
    check whether the home uses the same fuel for DHW as for heating. If not, anhu=0.

    From an OO design viewpoint, I don't see Summer_billingPeriods as a direct property 
    of the home. Rather, it's a property of the Location (an object defining the weather 
    station, and the Winter, Summer and Shoulder billing periods. Of course, Location
      would be a property of the Home.
    """

    def _calculate_avg_non_heating_usage(self) -> None:
        """
        Calculate avg non heating usage for this Home
        Args:
        #use_same_fuel_DHW_heating
        """

        if self.fuel_type == FuelType.GAS:
            self.avg_non_heating_usage = self.avg_summer_usage
        elif self.has_boiler_for_dhw and self.same_fuel_dhw_heating:
            fuel_multiplier = 1  # default multiplier, for oil, placeholder number
            if self.fuel_type == FuelType.PROPANE:
                fuel_multiplier = 2  # a placeholder number
            self.avg_non_heating_usage = self._calculate_boiler_usage(fuel_multiplier)
        else:
            self.avg_non_heating_usage = 0

    def _calculate_balance_point_and_ua(
        self,
        initial_balance_point_sensitivity: float = 2,
        stdev_pct_max: float = 0.10,
        max_stdev_pct_diff: float = 0.01,
        next_balance_point_sensitivity: float = 0.5,
    ) -> None:
        """
        Calculates the estimated balance point and UA coefficient for
        the home, removing UA outliers based on a normalized standard
        deviation threshold.
        """
        self.uas = [bp.ua for bp in self.bills_winter]
        self.avg_ua = sts.mean(self.uas)
        self.stdev_pct = sts.pstdev(self.uas) / self.avg_ua
        self._refine_balance_point(initial_balance_point_sensitivity)

        while self.stdev_pct > stdev_pct_max:
            biggest_outlier_idx = np.argmax(
                [abs(bill.ua - self.avg_ua) for bill in self.bills_winter]
            )
            outlier = self.bills_winter.pop(
                biggest_outlier_idx
            )  # removes the biggest outlier
            uas_i = [bp.ua for bp in self.bills_winter]
            avg_ua_i = sts.mean(uas_i)
            stdev_pct_i = sts.pstdev(uas_i) / avg_ua_i
            if (
                self.stdev_pct - stdev_pct_i < max_stdev_pct_diff
            ):  # if it's a small enough change
                self.bills_winter.append(
                    outlier
                )  # then it's not worth removing it, and we exit
                break  # may want some kind of warning to be raised as well
            else:
                self.uas, self.avg_ua, self.stdev_pct = uas_i, avg_ua_i, stdev_pct_i

            self._refine_balance_point(next_balance_point_sensitivity)

    def _refine_balance_point(self, balance_point_sensitivity: float) -> None:
        """
        Tries different balance points plus or minus a given number
        of degrees, choosing whichever one minimizes the standard
        deviation of the UAs.
        """
        directions_to_check = [1, -1]

        while directions_to_check:
            bp_i = (
                self.balance_point + directions_to_check[0] * balance_point_sensitivity
            )

            if bp_i > self.thermostat_set_point:
                break  # may want to raise some kind of warning as well

            period_hdds_i = [
                period_hdd(bill.avg_temps, bp_i) for bill in self.bills_winter
            ]
            uas_i = [
                bill.partial_ua / period_hdds_i[n]
                for n, bill in enumerate(self.bills_winter)
            ]
            avg_ua_i = sts.mean(uas_i)
            stdev_pct_i = sts.pstdev(uas_i) / avg_ua_i

            if stdev_pct_i >= self.stdev_pct:
                directions_to_check.pop(0)
            else:
                self.balance_point, self.avg_ua, self.stdev_pct = (
                    bp_i,
                    avg_ua_i,
                    stdev_pct_i,
                )

                for n, bill in enumerate(self.bills_winter):
                    bill.total_hdd = period_hdds_i[n]
                    bill.ua = uas_i[n]

                if len(directions_to_check) == 2:
                    directions_to_check.pop(-1)

    def calculate(
        self,
        initial_balance_point_sensitivity: float = 2,
        stdev_pct_max: float = 0.10,
        max_stdev_pct_diff: float = 0.01,
        next_balance_point_sensitivity: float = 0.5,
    ) -> None:
        """
        For this Home, calculates avg non heating usage and then the estimated balance point
        and UA coefficient for the home, removing UA outliers based on a normalized standard
        deviation threshold.
        """
        self._calculate_avg_non_heating_usage()
        self._calculate_balance_point_and_ua(
            initial_balance_point_sensitivity,
            stdev_pct_max,
            max_stdev_pct_diff,
            next_balance_point_sensitivity,
        )

    def initialize_ua(self, billing_period: BillingPeriod) -> None:
        """
        Average heating usage, partial UA, initial UA. requires that
        self.home have non heating usage calculated.
        """
        billing_period.avg_heating_usage = (
            billing_period.usage / billing_period.days
        ) - self.avg_non_heating_usage
        billing_period.partial_ua = self.calculate_partial_ua(billing_period)
        billing_period.ua = billing_period.partial_ua / billing_period.total_hdd

    def calculate_partial_ua(self, billing_period: BillingPeriod) -> float:
        """
        The portion of UA that is not dependent on the balance point
        """
        return (
            billing_period.days
            * billing_period.avg_heating_usage
            * self.fuel_type.value
            * self.heat_sys_efficiency
            / 24
        )


class BillingPeriod:
    avg_heating_usage: float
    partial_ua: float
    ua: float

    def __init__(
        self,
        avg_temps: List[float],
        usage: float,
        balance_point: float,
        analysis_type: AnalysisType,
    ) -> None:
        self.avg_temps = avg_temps
        self.usage = usage
        self.balance_point = balance_point
        self.analysis_type = analysis_type

        self.days = len(self.avg_temps)
        self.total_hdd = period_hdd(self.avg_temps, self.balance_point)

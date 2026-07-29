import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from house_vs_stocks import (
    SimulationConfig,
    annual_to_monthly_rate,
    annuity_payment,
    payoff_months,
    load_config_state,
    save_config_state,
    simulate,
)


class SimulationTests(unittest.TestCase):
    def test_default_tracks_start_at_same_net_worth(self):
        result = simulate(SimulationConfig())
        self.assertAlmostEqual(result.homeowner_net_worth[0], 100_000)
        self.assertAlmostEqual(result.stock_net_worth[0], 100_000)
        self.assertAlmostEqual(
            result.homeowner_with_family_gift_net_worth[0], 400_000
        )

    def test_default_appreciation_triples_house_and_loans_are_repaid(self):
        result = simulate(SimulationConfig())
        self.assertAlmostEqual(result.house_values[-1], 4_500_000, places=5)
        self.assertAlmostEqual(result.mortgage_balances[-1], 0, places=5)
        self.assertAlmostEqual(result.gap_loan_balances[-1], 0, places=5)
        self.assertGreater(result.homeowner_net_worth[-1], 4_500_000)
        self.assertGreater(
            result.homeowner_with_family_gift_net_worth[-1], 4_500_000
        )

    def test_house_appreciation_changes_final_house_value(self):
        flat = simulate(SimulationConfig(house_annual_appreciation=0))
        growing = simulate(SimulationConfig(house_annual_appreciation=0.06))
        self.assertAlmostEqual(flat.house_values[-1], 1_500_000)
        self.assertGreater(growing.house_values[-1], flat.house_values[-1])

    def test_family_gift_line_excludes_gap_liability(self):
        result = simulate(SimulationConfig())
        for borrowed, gifted, gap_balance in zip(
            result.homeowner_net_worth,
            result.homeowner_with_family_gift_net_worth,
            result.gap_loan_balances,
        ):
            self.assertAlmostEqual(gifted - borrowed, gap_balance, places=5)

    def test_payment_mode_calculates_payoff_time(self):
        config = SimulationConfig(mortgage_mode="payment")
        result = simulate(config)
        monthly_rate = annual_to_monthly_rate(result.mortgage_annual_rate)
        expected_months = payoff_months(
            config.house_price - config.down_payment,
            monthly_rate,
            config.mortgage_monthly_payment,
        )
        self.assertAlmostEqual(result.mortgage_payoff_months, expected_months)
        self.assertEqual(
            result.mortgage_monthly_payment, config.mortgage_monthly_payment
        )

    def test_term_mode_calculates_monthly_payment(self):
        config = SimulationConfig(
            mortgage_mode="term",
            mortgage_years=20,
            mortgage_annual_rate=0.06,
        )
        result = simulate(config)
        expected_payment = annuity_payment(
            config.house_price - config.down_payment,
            annual_to_monthly_rate(config.mortgage_annual_rate),
            20 * 12,
        )
        self.assertAlmostEqual(result.mortgage_monthly_payment, expected_payment)
        self.assertEqual(result.mortgage_payoff_months, 20 * 12)

    def test_payment_below_interest_never_pays_off(self):
        result = simulate(
            SimulationConfig(
                mortgage_mode="payment",
                mortgage_monthly_payment=3_000,
                mortgage_annual_rate=0.10,
            )
        )
        self.assertEqual(result.mortgage_payoff_months, float("inf"))
        self.assertGreater(result.mortgage_balances[-1], result.mortgage_balances[0])

    def test_stock_contribution_is_independent_of_mortgage(self):
        contribution = 3_700
        first = simulate(
            SimulationConfig(
                stock_monthly_contribution=contribution,
                starting_monthly_rent=4_000,
                mortgage_monthly_payment=7_500,
            )
        )
        second = simulate(
            SimulationConfig(
                stock_monthly_contribution=contribution,
                starting_monthly_rent=4_000,
                mortgage_monthly_payment=15_000,
            )
        )
        self.assertEqual(first.stock_contributions, second.stock_contributions)
        self.assertEqual(first.stock_net_worth, second.stock_net_worth)

    def test_stock_addition_is_capped_by_renter_budget(self):
        result = simulate(
            SimulationConfig(
                monthly_income=10_000,
                monthly_expenses=4_000,
                starting_monthly_rent=5_000,
                stock_monthly_contribution=3_000,
                stock_loan_amount=0,
            )
        )
        self.assertEqual(result.stock_contributions[1], 1_000)
        self.assertEqual(result.renter_spendable_cash[1], 0)

    def test_budget_cash_for_homeowners_and_renter(self):
        result = simulate(SimulationConfig())
        expected_renter_cash = (
            20_000 - 8_000 - 5_000
            - result.stock_loan_monthly_payment
            - result.stock_contributions[1]
        )
        self.assertAlmostEqual(
            result.renter_spendable_cash[1], expected_renter_cash
        )
        self.assertAlmostEqual(result.homeowner_spendable_cash[1], 2_666.6666667)
        self.assertAlmostEqual(
            result.gifted_homeowner_spendable_cash[1], 3_500
        )

    def test_stock_loan_is_invested_and_also_recorded_as_debt(self):
        config = SimulationConfig(stock_loan_amount=200_000)
        result = simulate(config)
        self.assertEqual(result.stock_portfolio_values[0], 300_000)
        self.assertEqual(result.stock_loan_balances[0], 200_000)
        self.assertEqual(result.stock_net_worth[0], 100_000)

    def test_stock_loan_uses_spitzer_payment(self):
        config = SimulationConfig(
            stock_loan_amount=200_000,
            stock_loan_annual_rate=0.08,
            stock_loan_years=30,
        )
        result = simulate(config)
        expected = annuity_payment(
            200_000,
            annual_to_monthly_rate(0.08),
            30 * 12,
        )
        self.assertAlmostEqual(result.stock_loan_monthly_payment, expected)
        self.assertAlmostEqual(result.stock_loan_balances[-1], 0, places=5)

    def test_higher_stock_return_increases_final_stock_net_worth(self):
        lower = simulate(SimulationConfig(stock_annual_return=0.04))
        higher = simulate(SimulationConfig(stock_annual_return=0.10))
        self.assertGreater(higher.stock_net_worth[-1], lower.stock_net_worth[-1])

    def test_house_price_and_down_payment_set_both_loans(self):
        result = simulate(
            SimulationConfig(
                house_price=2_000_000,
                down_payment=500_000,
            )
        )
        self.assertEqual(result.mortgage_balances[0], 1_500_000)
        self.assertEqual(result.gap_loan_balances[0], 400_000)

    def test_homeowner_investment_is_added_to_net_worth(self):
        without_investing = simulate(
            SimulationConfig(homeowner_monthly_contribution=0)
        )
        with_investing = simulate(
            SimulationConfig(homeowner_monthly_contribution=1_000)
        )
        self.assertGreater(
            with_investing.homeowner_net_worth[-1],
            without_investing.homeowner_net_worth[-1],
        )
        self.assertGreater(
            with_investing.gifted_homeowner_portfolio_values[-1], 0
        )

    def test_configuration_state_round_trip(self):
        expected = SimulationConfig(
            monthly_income=42_000,
            house_price=2_500_000,
            down_payment=600_000,
            mortgage_mode="term",
            mortgage_years=25,
            homeowner_monthly_contribution=2_000,
        )
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            save_config_state(state_path, expected)
            actual = load_config_state(state_path, SimulationConfig())
        self.assertEqual(actual, expected)

    def test_down_payment_gap_interest_increases_payment(self):
        free_family_loan = simulate(
            SimulationConfig(gap_loan_annual_rate=0)
        )
        interest_bearing_loan = simulate(
            SimulationConfig(gap_loan_annual_rate=0.08)
        )
        self.assertGreater(
            interest_bearing_loan.gap_loan_monthly_payment,
            free_family_loan.gap_loan_monthly_payment,
        )
        self.assertLess(
            interest_bearing_loan.homeowner_spendable_cash[1],
            free_family_loan.homeowner_spendable_cash[1],
        )

    def test_month_zero_through_month_360_are_present(self):
        result = simulate(SimulationConfig())
        self.assertEqual(len(result.months), 361)
        self.assertEqual(result.months[0], 0)
        self.assertEqual(result.months[-1], 360)


if __name__ == "__main__":
    unittest.main()

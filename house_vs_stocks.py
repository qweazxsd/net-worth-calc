"""Compare buying a home with renting and investing over time.

The model uses monthly periods and includes month 0.  Amounts are in NIS.
Edit the defaults in SimulationConfig or pass command-line arguments.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons, Slider


@dataclass(frozen=True)
class SimulationConfig:
    years: int = 30
    starting_cash: float = 100_000
    monthly_income: float = 20_000
    monthly_expenses: float = 8_000

    house_price: float = 1_500_000
    down_payment: float = 400_000
    # Equivalent to exactly tripling over 30 years.
    house_annual_appreciation: float = 3 ** (1 / 30) - 1
    mortgage_mode: str = "payment"
    mortgage_monthly_payment: float = 7_500
    mortgage_years: float = 30
    mortgage_annual_rate: float = 0.05

    # The buyer has only starting_cash, so the rest of the down payment is debt.
    # A 0% default represents an interest-free family/other loan, not free money.
    gap_loan_annual_rate: float = 0.0
    gap_loan_years: int = 30

    stock_annual_return: float = 0.07
    stock_monthly_contribution: float = 2_500
    stock_loan_amount: float = 200_000
    stock_loan_annual_rate: float = 0.08
    stock_loan_years: int = 30
    homeowner_monthly_contribution: float = 1_000
    starting_monthly_rent: float = 5_000
    annual_rent_increase: float = 0.02


@dataclass
class SimulationResult:
    months: list[int]
    house_values: list[float]
    mortgage_balances: list[float]
    gap_loan_balances: list[float]
    homeowner_net_worth: list[float]
    homeowner_with_family_gift_net_worth: list[float]
    homeowner_portfolio_values: list[float]
    gifted_homeowner_portfolio_values: list[float]
    homeowner_stock_contributions: list[float]
    gifted_homeowner_stock_contributions: list[float]
    stock_net_worth: list[float]
    stock_portfolio_values: list[float]
    stock_loan_balances: list[float]
    rents: list[float]
    stock_contributions: list[float]
    renter_spendable_cash: list[float]
    homeowner_spendable_cash: list[float]
    gifted_homeowner_spendable_cash: list[float]
    mortgage_annual_rate: float
    mortgage_monthly_payment: float
    mortgage_payoff_months: float
    gap_loan_monthly_payment: float
    stock_loan_monthly_payment: float


DEFAULT_STATE_PATH = Path(__file__).with_name("house_vs_stocks_state.json")


def load_config_state(
    state_path: Path, fallback: SimulationConfig
) -> SimulationConfig:
    """Load known configuration fields, ignoring an invalid saved state."""
    if not state_path.exists():
        return fallback
    try:
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        valid_names = {field.name for field in fields(SimulationConfig)}
        values = {
            name: value
            for name, value in saved.items()
            if name in valid_names
        }
        return replace(fallback, **values)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"Could not load saved state from {state_path}: {error}")
        return fallback


def save_config_state(state_path: Path, config: SimulationConfig) -> None:
    """Save the current interactive configuration as readable JSON."""
    try:
        state_path.write_text(
            json.dumps(asdict(config), indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        print(f"Could not save state to {state_path}: {error}")


def annual_to_monthly_rate(annual_effective_rate: float) -> float:
    """Convert an effective annual rate to an equivalent monthly rate."""
    if annual_effective_rate <= -1:
        raise ValueError("An annual rate must be greater than -100%.")
    return (1 + annual_effective_rate) ** (1 / 12) - 1


def annuity_payment(principal: float, monthly_rate: float, months: int) -> float:
    """Fixed Spitzer/annuity payment."""
    if principal <= 0:
        return 0.0
    if months <= 0:
        raise ValueError("Loan term must be positive.")
    if abs(monthly_rate) < 1e-15:
        return principal / months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -months)


def payoff_months(
    principal: float, monthly_rate: float, monthly_payment: float
) -> float:
    """Return the mathematical payoff time, or infinity if debt never falls."""
    if monthly_payment <= 0:
        return math.inf
    if abs(monthly_rate) < 1e-15:
        return principal / monthly_payment
    if monthly_payment <= principal * monthly_rate:
        return math.inf
    return -math.log(1 - principal * monthly_rate / monthly_payment) / math.log(
        1 + monthly_rate
    )


def simulate(config: SimulationConfig) -> SimulationResult:
    if config.starting_cash < 0:
        raise ValueError("Starting cash cannot be negative.")
    if config.down_payment < config.starting_cash:
        raise ValueError(
            "This model expects the down payment to be at least the starting cash."
        )
    if config.down_payment >= config.house_price:
        raise ValueError("Down payment must be lower than the house price.")
    if config.house_annual_appreciation <= -1:
        raise ValueError("Annual house appreciation must be greater than -100%.")
    if config.years <= 0 or config.gap_loan_years <= 0:
        raise ValueError("Simulation and loan terms must be positive.")
    if config.mortgage_mode not in {"payment", "term"}:
        raise ValueError("Mortgage mode must be 'payment' or 'term'.")
    if config.mortgage_annual_rate < 0:
        raise ValueError("Mortgage interest rate cannot be negative.")
    if config.stock_monthly_contribution < 0:
        raise ValueError("Monthly stock contribution cannot be negative.")
    if config.homeowner_monthly_contribution < 0:
        raise ValueError("Monthly homeowner contribution cannot be negative.")
    if config.monthly_income < 0 or config.monthly_expenses < 0:
        raise ValueError("Income and expenses cannot be negative.")
    if config.stock_loan_amount < 0 or config.stock_loan_annual_rate < 0:
        raise ValueError("Stock loan amount and interest cannot be negative.")
    if config.stock_loan_years <= 0:
        raise ValueError("Stock loan term must be positive.")

    total_months = config.years * 12
    mortgage_principal = config.house_price - config.down_payment
    mortgage_monthly_rate = annual_to_monthly_rate(config.mortgage_annual_rate)
    if config.mortgage_mode == "term":
        mortgage_term_months = max(1, round(config.mortgage_years * 12))
        mortgage_payment = annuity_payment(
            mortgage_principal, mortgage_monthly_rate, mortgage_term_months
        )
        mortgage_payoff_months = float(mortgage_term_months)
    else:
        mortgage_payment = config.mortgage_monthly_payment
        mortgage_payoff_months = payoff_months(
            mortgage_principal, mortgage_monthly_rate, mortgage_payment
        )

    gap_principal = config.down_payment - config.starting_cash
    gap_months = config.gap_loan_years * 12
    gap_monthly_rate = annual_to_monthly_rate(config.gap_loan_annual_rate)
    gap_payment = annuity_payment(gap_principal, gap_monthly_rate, gap_months)

    house_monthly_growth = annual_to_monthly_rate(
        config.house_annual_appreciation
    )
    stock_monthly_return = annual_to_monthly_rate(config.stock_annual_return)
    stock_loan_months = config.stock_loan_years * 12
    stock_loan_monthly_rate = annual_to_monthly_rate(
        config.stock_loan_annual_rate
    )
    stock_loan_payment = annuity_payment(
        config.stock_loan_amount,
        stock_loan_monthly_rate,
        stock_loan_months,
    )

    months = list(range(total_months + 1))
    house_values = [config.house_price]
    mortgage_balances = [mortgage_principal]
    gap_balances = [gap_principal]
    homeowner_net_worth = [
        config.house_price - mortgage_principal - gap_principal
    ]
    homeowner_with_family_gift_net_worth = [
        config.house_price - mortgage_principal
    ]
    homeowner_portfolio = 0.0
    gifted_homeowner_portfolio = 0.0
    homeowner_portfolios = [homeowner_portfolio]
    gifted_homeowner_portfolios = [gifted_homeowner_portfolio]
    homeowner_stock_contributions = [0.0]
    gifted_homeowner_stock_contributions = [0.0]
    portfolio = config.starting_cash + config.stock_loan_amount
    stock_loan_balance = config.stock_loan_amount
    stock_portfolio_values = [portfolio]
    stock_loan_balances = [stock_loan_balance]
    stock_net_worth = [portfolio - stock_loan_balance]
    rents = [config.starting_monthly_rent]
    stock_contributions = [0.0]
    renter_spendable = [0.0]
    homeowner_spendable = [0.0]
    gifted_homeowner_spendable = [0.0]

    house_value = config.house_price
    mortgage_balance = mortgage_principal
    gap_balance = gap_principal
    for month in range(1, total_months + 1):
        house_value *= 1 + house_monthly_growth

        mortgage_payment_this_month = 0.0
        if mortgage_balance > 0:
            balance_after_interest = mortgage_balance * (
                1 + mortgage_monthly_rate
            )
            mortgage_payment_this_month = min(
                mortgage_payment, balance_after_interest
            )
            mortgage_balance = max(
                0.0, balance_after_interest - mortgage_payment_this_month
            )

        if month <= gap_months:
            gap_balance = max(
                0.0, gap_balance * (1 + gap_monthly_rate) - gap_payment
            )
            gap_payment_this_month = gap_payment
        else:
            gap_payment_this_month = 0.0

        stock_loan_payment_this_month = 0.0
        if stock_loan_balance > 0:
            stock_loan_after_interest = stock_loan_balance * (
                1 + stock_loan_monthly_rate
            )
            stock_loan_payment_this_month = min(
                stock_loan_payment, stock_loan_after_interest
            )
            stock_loan_balance = max(
                0.0,
                stock_loan_after_interest - stock_loan_payment_this_month,
            )

        # The stock slider is independent of the mortgage. The actual
        # contribution is capped by cash left after rent and other expenses.
        rent = config.starting_monthly_rent * (
            (1 + config.annual_rent_increase) ** ((month - 1) // 12)
        )
        renter_cash_before_investing = (
            config.monthly_income
            - config.monthly_expenses
            - rent
            - stock_loan_payment_this_month
        )
        stock_contribution = min(
            config.stock_monthly_contribution,
            max(0.0, renter_cash_before_investing),
        )
        renter_cash_to_spend = renter_cash_before_investing - stock_contribution
        homeowner_cash_before_investing = (
            config.monthly_income
            - config.monthly_expenses
            - mortgage_payment_this_month
            - gap_payment_this_month
        )
        gifted_homeowner_cash_before_investing = (
            config.monthly_income
            - config.monthly_expenses
            - mortgage_payment_this_month
        )
        homeowner_contribution = min(
            config.homeowner_monthly_contribution,
            max(0.0, homeowner_cash_before_investing),
        )
        gifted_homeowner_contribution = min(
            config.homeowner_monthly_contribution,
            max(0.0, gifted_homeowner_cash_before_investing),
        )
        homeowner_cash_to_spend = (
            homeowner_cash_before_investing - homeowner_contribution
        )
        gifted_homeowner_cash_to_spend = (
            gifted_homeowner_cash_before_investing
            - gifted_homeowner_contribution
        )

        # Monthly market return, followed by an end-of-month contribution.
        portfolio = portfolio * (1 + stock_monthly_return) + stock_contribution
        homeowner_portfolio = (
            homeowner_portfolio * (1 + stock_monthly_return)
            + homeowner_contribution
        )
        gifted_homeowner_portfolio = (
            gifted_homeowner_portfolio * (1 + stock_monthly_return)
            + gifted_homeowner_contribution
        )

        house_values.append(house_value)
        mortgage_balances.append(mortgage_balance)
        gap_balances.append(gap_balance)
        homeowner_net_worth.append(
            house_value
            - mortgage_balance
            - gap_balance
            + homeowner_portfolio
        )
        homeowner_with_family_gift_net_worth.append(
            house_value - mortgage_balance + gifted_homeowner_portfolio
        )
        homeowner_portfolios.append(homeowner_portfolio)
        gifted_homeowner_portfolios.append(gifted_homeowner_portfolio)
        homeowner_stock_contributions.append(homeowner_contribution)
        gifted_homeowner_stock_contributions.append(
            gifted_homeowner_contribution
        )
        stock_portfolio_values.append(portfolio)
        stock_loan_balances.append(stock_loan_balance)
        stock_net_worth.append(portfolio - stock_loan_balance)
        rents.append(rent)
        stock_contributions.append(stock_contribution)
        renter_spendable.append(renter_cash_to_spend)
        homeowner_spendable.append(homeowner_cash_to_spend)
        gifted_homeowner_spendable.append(gifted_homeowner_cash_to_spend)

    return SimulationResult(
        months=months,
        house_values=house_values,
        mortgage_balances=mortgage_balances,
        gap_loan_balances=gap_balances,
        homeowner_net_worth=homeowner_net_worth,
        homeowner_with_family_gift_net_worth=homeowner_with_family_gift_net_worth,
        homeowner_portfolio_values=homeowner_portfolios,
        gifted_homeowner_portfolio_values=gifted_homeowner_portfolios,
        homeowner_stock_contributions=homeowner_stock_contributions,
        gifted_homeowner_stock_contributions=gifted_homeowner_stock_contributions,
        stock_net_worth=stock_net_worth,
        stock_portfolio_values=stock_portfolio_values,
        stock_loan_balances=stock_loan_balances,
        rents=rents,
        stock_contributions=stock_contributions,
        renter_spendable_cash=renter_spendable,
        homeowner_spendable_cash=homeowner_spendable,
        gifted_homeowner_spendable_cash=gifted_homeowner_spendable,
        mortgage_annual_rate=config.mortgage_annual_rate,
        mortgage_monthly_payment=mortgage_payment,
        mortgage_payoff_months=mortgage_payoff_months,
        gap_loan_monthly_payment=gap_payment,
        stock_loan_monthly_payment=stock_loan_payment,
    )


def save_csv(result: SimulationResult, output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "month",
                "year",
                "house_value",
                "mortgage_balance",
                "down_payment_gap_balance",
                "homeowner_net_worth",
                "homeowner_with_family_gift_net_worth",
                "homeowner_stock_portfolio",
                "gifted_homeowner_stock_portfolio",
                "homeowner_stock_contribution",
                "gifted_homeowner_stock_contribution",
                "stock_net_worth",
                "gross_stock_portfolio",
                "stock_loan_balance",
                "monthly_rent",
                "stock_contribution",
                "renter_spendable_cash",
                "homeowner_spendable_cash",
                "gifted_homeowner_spendable_cash",
            ]
        )
        for i, month in enumerate(result.months):
            writer.writerow(
                [
                    month,
                    month / 12,
                    result.house_values[i],
                    result.mortgage_balances[i],
                    result.gap_loan_balances[i],
                    result.homeowner_net_worth[i],
                    result.homeowner_with_family_gift_net_worth[i],
                    result.homeowner_portfolio_values[i],
                    result.gifted_homeowner_portfolio_values[i],
                    result.homeowner_stock_contributions[i],
                    result.gifted_homeowner_stock_contributions[i],
                    result.stock_net_worth[i],
                    result.stock_portfolio_values[i],
                    result.stock_loan_balances[i],
                    result.rents[i],
                    result.stock_contributions[i],
                    result.renter_spendable_cash[i],
                    result.homeowner_spendable_cash[i],
                    result.gifted_homeowner_spendable_cash[i],
                ]
            )


def mortgage_summary(result: SimulationResult) -> str:
    if math.isinf(result.mortgage_payoff_months):
        payoff = "never (payment does not cover interest)"
    else:
        payoff = f"{result.mortgage_payoff_months / 12:.1f} years"
    return (
        f"Payment: NIS {result.mortgage_monthly_payment:,.0f}/month\n"
        f"Payoff: {payoff}\n"
        f"Interest: {result.mortgage_annual_rate:.2%}\n"
        f"Final house value: NIS {result.house_values[-1]:,.0f}"
    )


def budget_summary(
    result: SimulationResult, monthly_income: float, monthly_expenses: float
) -> tuple[str, str, str]:
    """Show an explicit first-month cash-flow equation for every track."""
    month = 1
    mortgage_payment = (
        monthly_income
        - monthly_expenses
        - result.gifted_homeowner_stock_contributions[month]
        - result.gifted_homeowner_spendable_cash[month]
    )
    down_payment_gap = result.gap_loan_balances[0]
    stocks = (
        "STOCKS\n"
        f"Total income NIS {monthly_income:,.0f} - expenses NIS {monthly_expenses:,.0f}\n"
        f"- rent NIS {result.rents[month]:,.0f} - pay on loan "
        f"NIS {result.stock_loan_monthly_payment:,.0f}\n"
        f"- invested NIS {result.stock_contributions[month]:,.0f} "
        f"= cash to spend NIS {result.renter_spendable_cash[month]:,.0f}"
    )
    borrowed_house = (
        f"HOUSE - BORROWED NIS {down_payment_gap:,.0f}\n"
        f"Total income NIS {monthly_income:,.0f} - expenses NIS {monthly_expenses:,.0f}\n"
        f"- pay on house NIS {mortgage_payment:,.0f} "
        f"- pay on loan NIS {result.gap_loan_monthly_payment:,.0f}\n"
        f"- invested NIS {result.homeowner_stock_contributions[month]:,.0f} "
        f"= cash to spend NIS {result.homeowner_spendable_cash[month]:,.0f}"
    )
    gifted_house = (
        f"HOUSE - NIS {down_payment_gap:,.0f} FAMILY GIFT\n"
        f"Total income NIS {monthly_income:,.0f} - expenses NIS {monthly_expenses:,.0f}\n"
        f"- pay on house NIS {mortgage_payment:,.0f} - pay on loans NIS 0\n"
        f"- invested NIS {result.gifted_homeowner_stock_contributions[month]:,.0f} "
        f"= cash to spend NIS {result.gifted_homeowner_spendable_cash[month]:,.0f}"
    )
    return stocks, borrowed_house, gifted_house


def stock_loan_summary(result: SimulationResult, years: int) -> str:
    principal = result.stock_loan_balances[0]
    total_payments = result.stock_loan_monthly_payment * years * 12
    total_interest = max(0.0, total_payments - principal)
    return (
        f"Payment: NIS {result.stock_loan_monthly_payment:,.0f}/month\n"
        f"{years}-year interest total: NIS {total_interest:,.0f}"
    )


def plot_result(
    config: SimulationConfig,
    result: SimulationResult,
    output_path: Path,
    show: bool,
    state_path: Path | None = None,
) -> SimulationResult:
    years = [month / 12 for month in result.months]
    scale = 1_000_000

    fig, ax = plt.subplots(figsize=(15, 8.5))
    if show:
        fig.subplots_adjust(left=0.07, right=0.69, bottom=0.22, top=0.92)
    borrowed_line, = ax.plot(
        years,
        [value / scale for value in result.homeowner_net_worth],
        linewidth=2.5,
        label="Buy house: borrow missing down payment",
    )
    gift_line, = ax.plot(
        years,
        [
            value / scale
            for value in result.homeowner_with_family_gift_net_worth
        ],
        linewidth=2.5,
        linestyle="--",
        label="Buy house: family gift for missing down payment",
    )
    stock_line, = ax.plot(
        years,
        [value / scale for value in result.stock_net_worth],
        linewidth=2.5,
        label="Rent + invest: net worth",
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set(
        title="Buying a House vs. Renting and Investing",
        xlabel="Years from day 0",
        ylabel="Net worth (millions of NIS)",
    )
    ax.grid(alpha=0.25)
    ax.legend()
    if not show:
        fig.tight_layout()
        fig.savefig(output_path, dpi=160)
        plt.close(fig)
        return result

    income_ax = fig.add_axes([0.80, 0.91, 0.15, 0.014])
    expenses_ax = fig.add_axes([0.80, 0.875, 0.15, 0.014])
    stock_return_ax = fig.add_axes([0.80, 0.84, 0.15, 0.014])

    rent_ax = fig.add_axes([0.80, 0.77, 0.15, 0.014])
    stock_addition_ax = fig.add_axes([0.80, 0.735, 0.15, 0.014])
    stock_loan_amount_ax = fig.add_axes([0.80, 0.70, 0.15, 0.014])
    stock_loan_interest_ax = fig.add_axes([0.80, 0.665, 0.15, 0.014])

    house_price_ax = fig.add_axes([0.80, 0.56, 0.15, 0.014])
    down_payment_ax = fig.add_axes([0.80, 0.525, 0.15, 0.014])
    house_appreciation_ax = fig.add_axes([0.80, 0.49, 0.15, 0.014])
    homeowner_addition_ax = fig.add_axes([0.80, 0.455, 0.15, 0.014])
    gap_loan_interest_ax = fig.add_axes([0.80, 0.42, 0.15, 0.014])

    interest_ax = fig.add_axes([0.80, 0.335, 0.15, 0.014])
    payment_ax = fig.add_axes([0.80, 0.30, 0.15, 0.014])
    term_ax = fig.add_axes([0.80, 0.265, 0.15, 0.014])
    mode_ax = fig.add_axes([0.74, 0.175, 0.22, 0.07])

    fig.text(0.73, 0.945, "SHARED ASSUMPTIONS", fontsize=10, weight="bold")
    fig.text(0.73, 0.805, "RENTER / INVESTOR", fontsize=10, weight="bold")
    fig.text(0.73, 0.595, "HOMEOWNER", fontsize=10, weight="bold")
    fig.text(0.73, 0.375, "MORTGAGE", fontsize=10, weight="bold")
    summary = fig.text(
        0.73, 0.075, mortgage_summary(result), fontsize=8, wrap=True
    )
    stock_loan_text = fig.text(
        0.73,
        0.61,
        stock_loan_summary(result, config.stock_loan_years),
        fontsize=7.5,
    )
    initial_budget_texts = budget_summary(
        result, config.monthly_income, config.monthly_expenses
    )
    budget_texts = [
        fig.text(x, 0.025, text, fontsize=8.2, linespacing=1.15)
        for x, text in zip((0.04, 0.27, 0.50), initial_budget_texts)
    ]

    income_slider = Slider(
        income_ax,
        "Income",
        7_500,
        100_000,
        valinit=min(max(config.monthly_income, 7_500), 100_000),
        valstep=500,
        valfmt="NIS %.0f",
    )
    expenses_slider = Slider(
        expenses_ax,
        "Other expenses",
        1_000,
        100_000,
        valinit=min(max(config.monthly_expenses, 1_000), 100_000),
        valstep=500,
        valfmt="NIS %.0f",
    )
    rent_slider = Slider(
        rent_ax,
        "Rent",
        1_000,
        50_000,
        valinit=min(max(config.starting_monthly_rent, 1_000), 50_000),
        valstep=500,
        valfmt="NIS %.0f",
    )

    interest_slider = Slider(
        interest_ax,
        "Annual interest",
        0.0,
        12.0,
        valinit=config.mortgage_annual_rate * 100,
        valstep=0.1,
        valfmt="%.1f%%",
    )
    payment_slider = Slider(
        payment_ax,
        "Monthly payment",
        3_000,
        30_000,
        valinit=min(max(result.mortgage_monthly_payment, 3_000), 30_000),
        valstep=100,
        valfmt="NIS %.0f",
    )
    initial_term = (
        config.mortgage_years
        if config.mortgage_mode == "term"
        else result.mortgage_payoff_months / 12
    )
    if not math.isfinite(initial_term):
        initial_term = 60
    term_slider = Slider(
        term_ax,
        "Loan term",
        5,
        60,
        valinit=min(max(initial_term, 5), 60),
        valstep=1,
        valfmt="%.0f years",
    )
    house_appreciation_slider = Slider(
        house_appreciation_ax,
        "House appreciation",
        0,
        12,
        valinit=min(max(config.house_annual_appreciation * 100, 0), 12),
        valstep=0.1,
        valfmt="%.1f%%",
    )
    stock_addition_slider = Slider(
        stock_addition_ax,
        "Stock addition",
        0,
        100_000,
        valinit=min(max(config.stock_monthly_contribution, 0), 100_000),
        valstep=100,
        valfmt="NIS %.0f",
    )
    homeowner_addition_slider = Slider(
        homeowner_addition_ax,
        "Owner investment",
        0,
        100_000,
        valinit=min(max(config.homeowner_monthly_contribution, 0), 100_000),
        valstep=100,
        valfmt="NIS %.0f",
    )
    gap_loan_interest_slider = Slider(
        gap_loan_interest_ax,
        "Down-pay loan rate",
        0,
        20,
        valinit=min(max(config.gap_loan_annual_rate * 100, 0), 20),
        valstep=0.1,
        valfmt="%.1f%%",
    )
    stock_return_slider = Slider(
        stock_return_ax,
        "Stock return",
        0,
        20,
        valinit=min(max(config.stock_annual_return * 100, 0), 20),
        valstep=0.1,
        valfmt="%.1f%%",
    )
    house_price_slider = Slider(
        house_price_ax,
        "House price",
        500,
        10_000,
        valinit=min(max(config.house_price / 1_000, 500), 10_000),
        valstep=50,
        valfmt="NIS %.0fK",
    )
    down_payment_slider = Slider(
        down_payment_ax,
        "Down payment",
        100,
        5_000,
        valinit=min(max(config.down_payment / 1_000, 100), 5_000),
        valstep=50,
        valfmt="NIS %.0fK",
    )
    stock_loan_amount_slider = Slider(
        stock_loan_amount_ax,
        "Loan amount",
        0,
        1_000,
        valinit=min(max(config.stock_loan_amount / 1_000, 0), 1_000),
        valstep=10,
        valfmt="NIS %.0fK",
    )
    stock_loan_interest_slider = Slider(
        stock_loan_interest_ax,
        "Loan interest",
        0,
        25,
        valinit=min(max(config.stock_loan_annual_rate * 100, 0), 25),
        valstep=0.1,
        valfmt="%.1f%%",
    )
    mode_labels = ("Set monthly payment", "Set loan term")
    mode_buttons = RadioButtons(
        mode_ax,
        mode_labels,
        active=0 if config.mortgage_mode == "payment" else 1,
    )

    state = {
        "mode": config.mortgage_mode,
        "updating": False,
        "result": result,
        "config": config,
    }

    def show_active_control() -> None:
        payment_ax.set_facecolor(
            "#fff7cc" if state["mode"] == "payment" else "#eeeeee"
        )
        term_ax.set_facecolor(
            "#fff7cc" if state["mode"] == "term" else "#eeeeee"
        )

    def redraw(_value: object = None) -> None:
        if state["updating"]:
            return
        state["updating"] = True
        try:
            updated_config = replace(
                config,
                mortgage_mode=state["mode"],
                mortgage_annual_rate=interest_slider.val / 100,
                mortgage_monthly_payment=payment_slider.val,
                mortgage_years=term_slider.val,
                stock_monthly_contribution=stock_addition_slider.val,
                monthly_income=income_slider.val,
                monthly_expenses=expenses_slider.val,
                starting_monthly_rent=rent_slider.val,
                stock_loan_amount=stock_loan_amount_slider.val * 1_000,
                stock_loan_annual_rate=stock_loan_interest_slider.val / 100,
                stock_annual_return=stock_return_slider.val / 100,
                house_annual_appreciation=house_appreciation_slider.val / 100,
                house_price=house_price_slider.val * 1_000,
                down_payment=min(
                    down_payment_slider.val * 1_000,
                    house_price_slider.val * 1_000 - 50_000,
                ),
                homeowner_monthly_contribution=homeowner_addition_slider.val,
                gap_loan_annual_rate=gap_loan_interest_slider.val / 100,
            )
            if down_payment_slider.val * 1_000 != updated_config.down_payment:
                down_payment_slider.set_val(
                    updated_config.down_payment / 1_000
                )
            updated = simulate(updated_config)
            state["result"] = updated
            state["config"] = updated_config

            if state["mode"] == "payment":
                computed_years = updated.mortgage_payoff_months / 12
                if math.isfinite(computed_years):
                    term_slider.set_val(min(max(computed_years, 5), 60))
            else:
                payment_slider.set_val(
                    min(max(updated.mortgage_monthly_payment, 3_000), 30_000)
                )

            borrowed_line.set_ydata(
                [value / scale for value in updated.homeowner_net_worth]
            )
            gift_line.set_ydata(
                [
                    value / scale
                    for value in updated.homeowner_with_family_gift_net_worth
                ]
            )
            stock_line.set_ydata(
                [value / scale for value in updated.stock_net_worth]
            )
            summary.set_text(mortgage_summary(updated))
            updated_budget_texts = budget_summary(
                updated,
                updated_config.monthly_income,
                updated_config.monthly_expenses,
            )
            for text_artist, text_value in zip(
                budget_texts, updated_budget_texts
            ):
                text_artist.set_text(text_value)
            stock_loan_text.set_text(
                stock_loan_summary(updated, updated_config.stock_loan_years)
            )
            ax.relim()
            ax.autoscale_view()
            fig.canvas.draw_idle()
        finally:
            state["updating"] = False

    def change_mode(label: str) -> None:
        state["mode"] = "payment" if label == mode_labels[0] else "term"
        show_active_control()
        redraw()

    interest_slider.on_changed(redraw)
    income_slider.on_changed(redraw)
    expenses_slider.on_changed(redraw)
    rent_slider.on_changed(redraw)
    stock_return_slider.on_changed(redraw)
    homeowner_addition_slider.on_changed(redraw)
    gap_loan_interest_slider.on_changed(redraw)
    house_price_slider.on_changed(redraw)
    down_payment_slider.on_changed(redraw)
    stock_loan_amount_slider.on_changed(redraw)
    stock_loan_interest_slider.on_changed(redraw)
    house_appreciation_slider.on_changed(redraw)
    payment_slider.on_changed(
        lambda value: redraw(value) if state["mode"] == "payment" else None
    )
    term_slider.on_changed(
        lambda value: redraw(value) if state["mode"] == "term" else None
    )
    stock_addition_slider.on_changed(redraw)
    mode_buttons.on_clicked(change_mode)

    def save_current_state(_event: object = None) -> None:
        if state_path is not None:
            save_config_state(state_path, state["config"])

    fig.canvas.mpl_connect("close_event", save_current_state)
    show_active_control()
    plt.show()
    save_current_state()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return state["result"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare homeownership with renting and investing."
    )
    parser.add_argument("--years", type=int, default=30)
    parser.add_argument("--starting-cash", type=float, default=100_000)
    parser.add_argument("--income", type=float, default=20_000)
    parser.add_argument("--expenses", type=float, default=8_000)
    parser.add_argument("--house-price", type=float, default=1_500_000)
    parser.add_argument("--down-payment", type=float, default=400_000)
    parser.add_argument(
        "--house-appreciation",
        type=float,
        default=3 ** (1 / 30) - 1,
        help="Effective annual house appreciation rate.",
    )
    parser.add_argument(
        "--mortgage-mode", choices=("payment", "term"), default="payment"
    )
    parser.add_argument("--mortgage-payment", type=float, default=7_500)
    parser.add_argument("--mortgage-years", type=float, default=30)
    parser.add_argument("--mortgage-rate", type=float, default=0.05)
    parser.add_argument("--gap-loan-rate", type=float, default=0.0)
    parser.add_argument("--gap-loan-years", type=int, default=30)
    parser.add_argument("--stock-return", type=float, default=0.07)
    parser.add_argument("--stock-monthly-addition", type=float, default=2_500)
    parser.add_argument("--stock-loan-amount", type=float, default=200_000)
    parser.add_argument("--stock-loan-rate", type=float, default=0.08)
    parser.add_argument("--stock-loan-years", type=int, default=30)
    parser.add_argument("--homeowner-monthly-addition", type=float, default=1_000)
    parser.add_argument("--starting-rent", type=float, default=5_000)
    parser.add_argument("--rent-increase", type=float, default=0.02)
    parser.add_argument("--output", type=Path, default=Path("comparison.png"))
    parser.add_argument("--csv", type=Path, default=Path("comparison.csv"))
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help="JSON file used to restore and save interactive slider values.",
    )
    parser.add_argument(
        "--ignore-saved-state",
        action="store_true",
        help="Start from defaults/command-line values without loading saved state.",
    )
    parser.add_argument(
        "--no-show", action="store_true", help="Save files without opening the graph."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = SimulationConfig(
        years=args.years,
        starting_cash=args.starting_cash,
        monthly_income=args.income,
        monthly_expenses=args.expenses,
        house_price=args.house_price,
        down_payment=args.down_payment,
        house_annual_appreciation=args.house_appreciation,
        mortgage_mode=args.mortgage_mode,
        mortgage_monthly_payment=args.mortgage_payment,
        mortgage_years=args.mortgage_years,
        mortgage_annual_rate=args.mortgage_rate,
        gap_loan_annual_rate=args.gap_loan_rate,
        gap_loan_years=args.gap_loan_years,
        stock_annual_return=args.stock_return,
        stock_monthly_contribution=args.stock_monthly_addition,
        stock_loan_amount=args.stock_loan_amount,
        stock_loan_annual_rate=args.stock_loan_rate,
        stock_loan_years=args.stock_loan_years,
        homeowner_monthly_contribution=args.homeowner_monthly_addition,
        starting_monthly_rent=args.starting_rent,
        annual_rent_increase=args.rent_increase,
    )
    if not args.ignore_saved_state:
        config = load_config_state(args.state_file, config)
    result = simulate(config)
    result = plot_result(
        config,
        result,
        args.output,
        show=not args.no_show,
        state_path=args.state_file,
    )
    save_csv(result, args.csv)

    print(mortgage_summary(result))
    print(f"Stock addition: NIS {result.stock_contributions[-1]:,.0f}/month")
    print(stock_loan_summary(result, config.stock_loan_years))
    print(
        "Down-payment gap payment: "
        f"NIS {result.gap_loan_monthly_payment:,.2f}/month"
    )
    print(f"Final homeowner net worth: NIS {result.homeowner_net_worth[-1]:,.0f}")
    print(
        "Final homeowner net worth with family gift: "
        f"NIS {result.homeowner_with_family_gift_net_worth[-1]:,.0f}"
    )
    print(f"Final stock net worth: NIS {result.stock_net_worth[-1]:,.0f}")
    print(f"Saved graph to {args.output.resolve()}")
    print(f"Saved monthly data to {args.csv.resolve()}")


if __name__ == "__main__":
    main()

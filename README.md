# House vs. stocks

This monthly simulation compares:

- buying a NIS 1.5M home with a NIS 400K down payment and a fixed
  NIS 7,500 mortgage payment, when the missing NIS 300K is borrowed;
- buying the same home when the missing NIS 300K is a free family gift; and
- investing NIS 100K with an independently selected monthly contribution,
  while separately tracking rent.

The NIS 300K missing from the buyer's down payment is represented as a real
liability. By default it is a 0% loan paid over 30 years. Change
`--gap-loan-rate` if that money has a cost. The separate family-gift graph
line has no liability and no repayment for that NIS 300K.

## Run

```powershell
python -m pip install -r requirements.txt
python house_vs_stocks.py
```

The script opens a graph and saves `comparison.png` plus the full monthly
data in `comparison.csv`. The graph has two mortgage modes:

- **Set monthly payment:** move the payment slider and the calculated payoff
  time changes.
- **Set loan term:** move the term slider and the calculated monthly payment
  changes.

The annual mortgage-interest slider applies in both modes. Yellow marks the
active payment/term slider; gray marks the calculated one. If a selected
payment does not cover the monthly interest, the graph reports that the loan
will never be repaid.

The family-budget controls calculate the cash remaining each month:

- renter/investor: income minus expenses, rent, and the actual stock
  contribution;
- homeowner: income minus expenses, mortgage, and the borrowed-down-payment
  payment;
- homeowner with family gift: income minus expenses and mortgage.

The stock-addition slider selects the desired investment. The program caps
the actual contribution at the renter's available cash after rent and
expenses. A negative cash-to-spend value is shown as a budget shortfall.
Rent continues to increase by the configured annual rate.

The renter/investor can also borrow money for the portfolio. The entire loan
is invested at day 0, while the outstanding balance remains a liability:

```text
stock net worth = gross portfolio - remaining stock-loan balance
```

The loan uses a fixed-payment Spitzer schedule over 30 years. Its monthly
payment is deducted from the renter's budget before an optional stock
contribution. Sliders control the loan amount (NIS 0 to NIS 1M) and effective
annual interest (0% to 25%). The dashboard shows its monthly payment and total
scheduled interest.

The **Stock return** slider independently controls the portfolio's effective
annual return from 0% to 20%. The simulator converts it to an equivalent
monthly compounded return.

The **House appreciation** slider controls the home's effective annual
growth rate from 0% to 12%. The house compounds monthly, and its final value
is calculated and displayed instead of being fixed in advance.

The **House price** and **Down payment** sliders replace the fixed NIS 1.5M
price and NIS 400K bank requirement. The mortgage principal is always:

```text
house price - required down payment
```

The gap between the required down payment and the family's starting NIS 100K
is recalculated as either a loan or a family gift.

The **Owner investment** slider lets both homeowner tracks invest monthly in
the same stock portfolio return used by the renter. Each track's actual
investment is capped by its own available monthly cash. The investment
portfolio is included in that homeowner's net worth, and the bottom equations
show the investment before calculating cash to spend.

The **Down-pay loan rate** slider controls the effective annual interest on
the money borrowed to complete the required down payment. It uses a 30-year
Spitzer schedule. Setting it to 0% represents an interest-free family loan;
this is different from the family-gift track, where the money is never owed.

## Saved slider state

Closing the interactive window saves every slider value and the selected
mortgage mode to `house_vs_stocks_state.json` beside the script. The next run
loads those values automatically.

To temporarily start from the defaults without loading the saved file:

```powershell
python house_vs_stocks.py --ignore-saved-state
```

For non-interactive use:

```powershell
python house_vs_stocks.py --no-show
```

Rates are decimals: `0.07` means 7%. See every option with:

```powershell
python house_vs_stocks.py --help
```

Important defaults:

- stock return: 7% effective annually, compounded monthly;
- stock contribution: NIS 2,500/month;
- homeowner stock contribution: NIS 1,000/month;
- stock portfolio loan: NIS 200,000 at 8% effective annual interest for
  30 years;
- household income: NIS 20,000/month;
- general expenses: NIS 8,000/month;
- starting rent: NIS 5,000/month;
- rent increase: 2% once each year;
- home appreciation: approximately 3.73% effective annually, which happens
  to produce exactly 3x over the default 30 years;
- mortgage rate: 5% effective annually;
- mortgage mode: fixed NIS 7,500 monthly payment, with payoff time calculated.

Taxes, purchase/sale costs, maintenance, insurance, investment fees, and
taxes are not included yet.

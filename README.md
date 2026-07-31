# House vs. stocks

This monthly simulation compares:

- buying a NIS 1.5M home with a NIS 100K starting cash, a NIS 300K family
  gift covering the rest of the NIS 400K down payment, and a fixed NIS 7,500
  mortgage payment;
- investing the same NIS 100K with an independently selected monthly
  contribution, while separately tracking rent; and
- buying an identical NIS 1.5M investment property (same down payment,
  gift, and mortgage as the homeowner) while still renting your own home:
  you pay your own rent and collect the same rent from a tenant, so the two
  cancel out, leaving the same mortgage payment as the homeowner track.

The family gift covers whatever part of the down payment isn't covered by
the buyer's own starting cash. It is never owed back, so it isn't a
liability anywhere in the model.

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
- homeowner: income minus expenses and the mortgage payment;
- investment property: income minus expenses, minus the same mortgage
  payment as the homeowner, plus rental income, minus the rent you pay for
  your own home (the two rent terms use the same figure, so they cancel).

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

The **Starting cash** slider sets how much of the required down payment the
buyer covers themselves; it also seeds the renter/investor's initial stock
portfolio, since it's the same pool of cash either way. The family gift is
always calculated automatically as:

```text
family gift = required down payment - starting cash
```

Starting cash is capped at the current down payment, since the gift can't be
negative.

The **Owner investment** slider lets the homeowner invest monthly in the same
stock portfolio return used by the renter. The actual investment is capped
by the homeowner's own available monthly cash. The investment portfolio is
included in the homeowner's net worth, and the bottom equations show the
investment before calculating cash to spend.

The **Investor stock addition** slider does the same for the investment
property track, using its own available monthly cash (which, since rent
paid and rent collected cancel, works out to the same starting cash flow as
the homeowner track before either one invests).

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
- investor stock contribution: NIS 1,000/month;
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

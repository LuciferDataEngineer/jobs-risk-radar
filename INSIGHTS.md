# Insights

Computed from the committed snapshot on 9 November 2026 (Australia/Melbourne). Official state and national rates are the ABS seasonally adjusted unemployment rate for people aged 15 and over. Regional rates are the ABS modelled estimates and are not seasonally adjusted. A "point" is a percentage point of the unemployment rate.

The stakeholder pages round rates to one decimal place. Figures below use that same rounding unless a check needs the unrounded total.

## The national picture

- The official unemployment rate was **4.7%** in September 2026 (4.718% unrounded). A year earlier, in September 2025, it was **4.4%** (4.426%).
- The cash rate target was raised to **4.85%** effective 4 November 2026. That was the fifth increase of 2026. The month-end target moved from 3.60% in January to 3.85% in February, 4.10% in March, 4.35% in May, 4.60% in September and 4.85% in November. June and August were holds at 4.35%, and October stayed at 4.60%.
- The Reserve Bank's November 2026 Statement on Monetary Policy projects unemployment at 4.8% by December 2026 and about 5.1% by the end of 2028. The "bit over 5%" path is a two-year national projection, not a claim about next quarter.

## Where the states stand

Official rates, September 2025 and September 2026:

| State | Sep 2025 | Sep 2026 | Direction |
| --- | ---: | ---: | --- |
| New South Wales | 4.2% | 4.7% | up about 0.5 points |
| Victoria | 4.7% | 5.1% | up about 0.3 points |
| Queensland | 4.2% | 4.5% | up about 0.4 points |
| South Australia | 4.5% | 4.2% | down about 0.3 points |
| Western Australia | 4.3% | 4.2% | down about 0.1 points |
| Tasmania | 4.4% | 5.0% | up about 0.5 points |
| Australia | 4.4% | 4.7% | up about 0.3 points |

Victoria and Tasmania are already around 5%. New South Wales has had the largest rise of these six, half a point in a year. South Australia has improved. The Northern Territory and the ACT are not in this API extract, so they are not in the table. The Labour Force API returned no series for region codes 7 and 8 on this key.

National job vacancies were **321,500** in the September quarter of 2026, against **325,900** a year earlier. That is a small decline, not a collapse. Victoria's vacancies were slightly higher (77,500 against 74,800). The vacancy series is not what explains Victoria's higher unemployment rate.

Dwelling approvals are a sharper state contrast. Australia approved **18,318** dwellings in September 2026, close to **18,633** a year earlier. Victoria approved **3,918**, down from **5,588**, about **30%** lower. New South Wales was down about 6%. Queensland, South Australia and Western Australia were higher than a year earlier.

## Where regions have already moved

Across the 87 modelled regions in September 2026:

- Employment sums to **14,743.8 thousand**, the same Australia total printed in the ABS workbook. That is the reconciliation check in `reports/quality.json`.
- The unrounded median unemployment rate is **4.3%**. The lowest region is about **2.6%** and the highest, Queensland - Outback, is about **6.8%**. The ABS release text for September 2026 said the median across SA4s was 4.4% and the range was 2.6% to 6.8%. The range matches. The median here is the median of the unrounded rates.
- From June to September 2026 the typical region rose **0.2 points**, and **69%** of regions rose. In 2023, 2024 and 2025 the typical June-to-September move was about **0.07, 0.03 and 0.07 points**. The 2026 lift is larger than the same three months in those years. **23 regions** are up by half a point or more since June. About **4.0 million** people in the labour force live in those 23 regions, out of **15.5 million** in the regional total.

The sharpest June-to-September rises:

| Region | Rate in September | Change since June |
| --- | ---: | ---: |
| Sydney - Parramatta | 6.7% | +1.9 points |
| Sydney - Outer West and Blue Mountains | 4.9% | +1.5 points |
| Hunter Valley exc Newcastle | 5.2% | +1.2 points |
| Illawarra | 5.2% | +1.1 points |
| Sydney - Inner South West | 5.4% | +1.0 points |

Rates already above 6% include Queensland - Outback (6.8%), Sydney - Parramatta (6.7%), Melbourne - West (6.6%), Northern Territory - Outback (6.5%), Melbourne - South East (6.3%) and Ipswich (6.3%). These are modelled original rates, so a single three-month move can include the time of year. Parramatta's 1.9 point rise is far above the typical region and is the first place a New South Wales service response should look, with the usual caution about one modelled series.

## The next three months

The forecast is the change from September 2026 to December 2026. It is trained on every earlier quarter whose outcome is already in the snapshot, then given September's regional figures and the 4.85% cash rate now in force.

- The rate is expected to ease by more than 0.1 points in **78 of 87** regions. September to December has usually been a softer patch than June to September, and the outlook still says that.
- **Darwin** is the only region expected to rise by at least 0.1 points, about **0.2 points**, from **3.0%**. The chance the model puts on a rise of 0.3 points or more there is under 50%, so the site says "less sure".
- Several regions with rates already above 5%, including Moreton Bay - North and Wide Bay, are expected to ease by less than they did over the same months last year. A softer December is not the same as a return to last year's improvement.
- Places the model expects to ease still include regions that are high today. Melbourne - West, Melbourne - South East, Ipswich and Queensland - Outback need support because of the rate now, not because the outlook says December will be worse.

## How much to trust the ordering

On 26 quarter-ends from March 2020 to June 2026 (2,262 region-quarters):

- Average absolute error was **0.50 points**, against **0.60** for "repeat last year's move" and **0.72** for "repeat the last quarter".
- Average rank agreement with what then happened was **0.32**.
- When the outlook named the 10 regions with the biggest predicted moves, about **3** of them were actually in the 10 that moved the most. Chance, given 87 regions, would be about 1.
- A yes/no call for "rise of at least 0.3 points" was right **74%** of the time. Always saying "no" would have been right **76%** of the time, because only **24%** of those region-quarters rose that much. The site does not lead with that yes/no call.

The drift report compares scored quarters in 2020–2022 with 2024–2026 and flags a shift in **20 of 21** columns. The recent window, which includes the rate rises of 2026, does not look like the earlier window. That is a reason to keep the error figures next to the map, not a reason to hide the map.

## What a user of the briefing should do

- New South Wales: the state rate is up half a point in a year, and the largest regional jumps since June are in Sydney and the Hunter. Parramatta is the priority.
- Victoria: the state rate is 5.1%, Melbourne's west and south-east are already above 6% on the modelled estimates, and dwelling approvals are down about 30% on a year earlier. Vacancies at state level have not fallen.
- Tasmania: the official rate is 5.0%, up about half a point in a year.
- South Australia: the official rate has fallen, to 4.2%. Some Adelaide regions are still high on the modelled estimates, and several are not expected to get last year's end-of-year improvement.
- Darwin: low rate, and the only region the outlook still has rising. Watch it. Do not treat it as a crisis.
- Everywhere else: the central case for December is an easing. Do not move staff away from the high-rate regions on the strength of that.

These are descriptions of the published statistics and of one forecast checked against the published history. They are not a government instruction.

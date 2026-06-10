---
name: comp-bands-chile
description: |
  Compensation bands for product / tech leadership roles in Chile, in CLP
  GROSS MONTHLY (sueldo bruto mensual). Used by the Negotiation agent and
  by the Matcher to evaluate `target_min_comp_clp`. Numbers are inferred
  ranges from publicly observed Robert Half / PageGroup / Laborum / Glassdoor
  CL data and conversations with recruiters. Always sanity-check before
  using in a real negotiation.
---

# Skill: comp-bands-chile

## Core conventions (read this first)

- All figures are **CLP gross monthly** ("sueldo bruto mensual") unless
  noted. To get gross annual, multiply by 12 — but in Chile employers
  also typically pay a legal **gratificación** of up to 4.75 monthly minimum
  wages per year (≈ CLP 2.5M/yr cap as of 2024), often "garantizada"
  in tech roles. So real annual ≈ base × 12 + gratificación cap.
- Variable / bono is **expressed as % of annual base**. PM and Director
  roles in CL typically see 10-25% bono target; senior corporate roles
  (Falabella, BCI, banking) can reach 30-40%.
- Equity / stock options are rare outside Mercado Libre, NotCo, Cornershop,
  Globant and a handful of scale-ups. Don't anchor on it.
- Sign-on bonuses exist but are not standard. Always ask.
- 1 USD ≈ 950 CLP as a rough planning anchor (volatile — check).

## Ranges by role / seniority (CLP gross monthly)

> These are **inferred planning ranges**, not contracts. Width is wider
> than US/EU because the CL market is small and dispersed.

| Role | Seniority | Low | Mid | High | Variable % | Typical sector skew |
|---|---|---:|---:|---:|---:|---|
| Product Manager | mid | 3.5M | 4.5M | 5.5M | 10-15% | Scale-ups, SaaS |
| Product Manager | senior | 5.0M | 6.5M | 8.0M | 10-20% | Cross-sector |
| Senior PM / Group PM | senior | 7.0M | 8.5M | 10.0M | 15-20% | ML, NotCo, Cornershop, Buk |
| Director of Product | director | 8.0M | 10.5M | 13.0M | 20-30% | Banking, retail, scale-ups |
| VP Product | vp | 11.0M | 14.0M | 18.0M+ | 25-40% | Top scale-ups, conglomerates |
| Head of Product (small co.) | director | 6.5M | 8.5M | 11.0M | 10-20% | Series A/B startups |
| Chief Product Officer | c-level | 14.0M | 18.0M | 25.0M+ | 30-50% + equity | Unicorns, top banks |

Adjacent leadership (rough anchors):

| Role | Seniority | Low | Mid | High |
|---|---|---:|---:|---:|
| Engineering Manager | senior | 5.5M | 7.0M | 9.0M |
| Director of Engineering | director | 8.5M | 11.0M | 14.0M |
| Data Lead | senior | 5.0M | 6.5M | 8.5M |
| Country Manager (subsidiary) | vp | 12.0M | 16.0M | 22.0M+ |

## Sector adjustments (apply as multipliers)

- **Banking / fintech / mining**: +10-20% on base, larger bono.
- **Government, NGO, education**: -10-25%, but better benefits / stability.
- **Foreign tech with CL office** (Globant, ThoughtWorks, AWS): +10-30%,
  may pay partial USD or USD-denominated.
- **Early-stage startups (Series A)**: -10-20% on base, equity to compensate
  (treat equity at 30-50% of paper value for planning).

## Total-comp calculation (planning template)

```
gross_annual_CLP = base_CLP_per_month * 12
                 + min(legal_gratificacion_cap, 4.75 * minimum_wage_per_month)
                 + variable_bonus_target_CLP
                 + sign_on_CLP            # one-time, amortize over tenure if needed
                 + equity_paper_value * 0.4   # haircut
```

USD equivalent (rough, for comparing offers vs US/EU):
```
usd_annual = gross_annual_CLP / USD_CLP_rate
```

## Negotiation levers beyond base (use these BEFORE walking away)

1. **Gratificación**: confirm it's the cap (4.75x minimum wage) and that
   it's *garantizada*, not contingent on company profit.
2. **Bono variable**: target %, KPIs, who measures, payout cadence.
   Negotiate for an **MBO** structure with clear, controllable KPIs.
3. **Vacaciones**: legal floor is 15 días hábiles/yr. Senior roles can ask
   for 20-25.
4. **Sign-on**: justify with notice-period loss or relocation. CLP 5-15M
   range is realistic at senior+.
5. **Equity / phantom**: rare, but ask. At scale-ups (Series B+) it's normal.
6. **Scope / title**: a "Senior PM" title at Falabella is meaningfully
   different from "Director" at a Series A. Title shapes the next move.
7. **Remoto / híbrido**: most CL companies now do 2-3 days/week. Full
   remote is negotiable; quantify it as ~CLP 200-400k/mo of value (transport,
   time, lunch).
8. **Fecha de inicio**: 1-2 months extra runway = real money.

## Sanity check rules the agent must apply

- If offer >= 90% of high-band → cap counter at +5-10% base, push harder
  on levers 2-7.
- If offer < low-band → counter +20-30% with explicit benchmark citation,
  and quantify the gap in writing.
- Never claim a competing offer that doesn't exist. Use "estoy en
  conversaciones avanzadas con otra empresa" only if literally true.
- If user provided `target_min_comp_clp`, walk-away ≥ that floor.

## Sources (consult periodically to refresh)

- Robert Half Chile salary guide (annual)
- PageGroup / Michael Page Latam tech salary report
- Laborum / Trabajando.com aggregate postings
- Glassdoor Chile (treat as noisy lower bound)
- Conversations with recruiters at PageGroup, Spencer Stuart, Egon Zehnder
- Levels.fyi for foreign tech subsidiaries

# Supported Assets

AT Exchange trades two things only: **cryptocurrency** and **gift cards**.

## Cryptocurrency

BTC, USDT, ETH, and SOL. Network for receiving each of these (e.g. "USDT on
TRC20 only") is confirmed per-transaction via get_payment_instructions, since
that depends on which wallet address the team has on file, which can change.

## Gift Cards

Amazon, Steam, and iTunes gift cards. Region/denomination restrictions:
TBD, confirm with the business owner.

## How rates work

Rates for each asset are set by the team and can change at any time, so
always check with get_rate rather than quoting a remembered number.

- Crypto rates are a price per unit (per 1 coin/token) in Naira.
- Gift card rates are Naira per $1 of face value (e.g. a rate of "₦700/$1"
  on a $100 card means ₦70,000).

For every asset, `buy` is the rate AT Exchange pays when a customer sells us
the asset, and `sell` is the rate AT Exchange charges when a customer buys
the asset from us. `buy` is always lower than `sell`, that gap is the
exchange's margin.

The current numbers in `data/rates.json` were seeded on 2026-09-08 from
public market data (Binance P2P USDT/NGN, spot BTC/ETH/SOL prices, and
typical Nigerian gift card resale rates) with a standard spread applied.
They're a starting point, not a guarantee, crypto and gift card markets move
daily. Check and update them regularly (see `workflows/manage_rates_and_knowledge_base.md`).

## Where payment/assets go

Where you send your payment or asset (if buying) or where you receive your
payout (if selling) isn't fixed information published here. It's looked up
fresh for every transaction request via get_payment_instructions, since the
team can update bank details or wallet addresses at any time. Never send
funds or a gift card code to an address that wasn't given to you as part of
an active transaction request in this chat.

---

## Not yet finalized, confirm with the business owner, don't guess

- Gift card region/country and denomination restrictions
- Crypto wallet addresses and networks (see `data/payment_methods.json`, still TBD)

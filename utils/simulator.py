class Simulator:
    """積立投資シミュレーター。

    資産を「現金資産」と「投資資産」に分けて管理する。
    - 毎月 monthly_budget（余剰資金）が入り、そのうち monthly_invest を積立に回す。
      残り（monthly_budget − monthly_invest）は現金として保有する。
    - 売却：投資資産の一部を現金化する。
    - 購入：現金の一部で投資信託を買い増す。
    - 積立変更：以降の毎月の積立額を変更する。
    含み損益は保有中の投資資産の取得原価（平均取得単価）に対する評価損益率で表す。
    """

    def __init__(self, initial_cash, monthly_budget):
        self.initial_cash = initial_cash
        self.monthly_budget = monthly_budget

    def simulate(self, timeline, decisions, initial_invest, initial_monthly_invest):
        initial_invest = max(0, min(initial_invest, self.initial_cash))
        monthly_invest = max(0, min(initial_monthly_invest, self.monthly_budget))

        price = 1.0
        units = initial_invest / price
        cash = self.initial_cash - initial_invest
        cost_basis = initial_invest  # 保有中の投資資産の取得原価（含み損益の基準）

        history = [self._state(0, price, units, cash, cost_basis, monthly_invest)]

        for month_data in timeline:
            month = month_data["month"]
            r = month_data["return"]

            # 1. 市場変動
            price *= (1 + r)

            # 2. 毎月の余剰資金：積立分を投資、残りは現金へ
            invest_amt = min(monthly_invest, self.monthly_budget)
            if invest_amt > 0:
                units += invest_amt / price
                cost_basis += invest_amt
            cash += (self.monthly_budget - invest_amt)

            # 3. この月にユーザーの行動があれば適用
            d = decisions.get(month)
            if d:
                # 積立設定の変更（以降の月に反映）
                if "monthly_invest" in d:
                    monthly_invest = max(0, min(d["monthly_invest"], self.monthly_budget))

                # 売却：投資資産を上限に現金化
                sell_amount = d.get("sell_amount", 0)
                if sell_amount and units > 0:
                    amount = min(sell_amount, units * price)
                    units_sold = amount / price
                    cost_basis -= cost_basis * (units_sold / units)
                    units -= units_sold
                    cash += amount

                # 購入：現金を上限に買い増し
                buy_amount = d.get("buy_amount", 0)
                if buy_amount:
                    amount = min(buy_amount, cash)
                    if amount > 0:
                        units += amount / price
                        cost_basis += amount
                        cash -= amount

            history.append(self._state(month, price, units, cash, cost_basis, monthly_invest))

        return history

    @staticmethod
    def _state(month, price, units, cash, cost_basis, monthly_invest):
        invest_value = units * price
        total = cash + invest_value
        pl_pct = ((invest_value - cost_basis) / cost_basis * 100) if cost_basis > 0 else 0.0
        return {
            "month": month,
            "price": price,
            "units": units,
            "cash": round(cash),
            "invest_value": round(invest_value),
            "total": round(total),
            "cost_basis": round(cost_basis),
            "pl_pct": round(pl_pct, 2),
            "monthly_invest": monthly_invest,
        }

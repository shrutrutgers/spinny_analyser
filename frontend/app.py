import os

import plotly.graph_objects as go
import requests
import streamlit as st

from finance import monthly_emi, remaining_balance


def get_backend_url() -> str:
    try:
        if "BACKEND_URL" in st.secrets:
            return st.secrets["BACKEND_URL"]
    except Exception:
        pass
    return os.environ.get("BACKEND_URL", "http://localhost:5000")


BACKEND_URL = get_backend_url()


def pick_buyback_value(schedule: dict, hold_months: int, price: int) -> tuple[int, int | None]:
    """Pick the scraped buyback value for the month closest to hold_months.
    Returns (amount, matched_month). matched_month is None if the schedule
    is empty (caller should fall back to a manual estimate)."""
    candidates = {
        int(month): entry["value"]
        for month, entry in schedule.items()
        if entry.get("value")
    }
    if not candidates:
        return int(price * 0.45), None
    closest_month = min(candidates, key=lambda m: abs(m - hold_months))
    return int(candidates[closest_month]), closest_month


st.set_page_config(page_title="Spinny Cost of Ownership", page_icon="🚗", layout="wide")

st.title("🚗 Spinny 2-Year Cost of Ownership")
st.caption(
    "Paste a Spinny used-car listing link to see what it will actually cost you "
    "to own for 2 years — EMI, maintenance, running costs, and Spinny's assured "
    "buyback, all in one number."
)

if "data" not in st.session_state:
    st.session_state["data"] = None
if "error" not in st.session_state:
    st.session_state["error"] = None

url = st.text_input(
    "Spinny listing URL",
    placeholder="https://www.spinny.com/buy-used-cars/.../31472510/",
)
analyze = st.button("Analyze", type="primary")

if analyze:
    if not url.strip():
        st.warning("Paste a Spinny listing URL first.")
    else:
        with st.spinner("Scraping listing from Spinny..."):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/api/scrape", json={"url": url.strip()}, timeout=30
                )
                if resp.status_code == 200:
                    st.session_state["data"] = resp.json()
                    st.session_state["error"] = None
                else:
                    st.session_state["data"] = None
                    try:
                        st.session_state["error"] = resp.json().get("error", "Unknown error")
                    except ValueError:
                        st.session_state["error"] = f"Backend error (HTTP {resp.status_code})"
            except requests.RequestException as exc:
                st.session_state["data"] = None
                st.session_state["error"] = f"Could not reach the backend at {BACKEND_URL}: {exc}"

if st.session_state["error"]:
    st.error(st.session_state["error"])

data = st.session_state["data"]

if data:
    car = data["car"]
    pricing = data["pricing"]
    finance_d = data["finance"]
    buyback = data["buyback"]
    maintenance = data["maintenance"]
    rsa = data["rsa"]
    warranty = data["extended_warranty"]
    price = pricing["listing_price"] or 0

    st.subheader(car.get("title") or "Car")
    cols = st.columns(6)
    cols[0].metric("Year", car.get("make_year") or "—")
    cols[1].metric("Km driven", f"{car['km_driven']:,}" if car.get("km_driven") else "—")
    cols[2].metric("Fuel", (car.get("fuel_type") or "—").title())
    cols[3].metric("Transmission", (car.get("transmission") or "—").title())
    cols[4].metric("Owners", car.get("no_of_owners") or "—")
    cols[5].metric("City", car.get("city") or "—")

    st.divider()

    p1, p2, p3 = st.columns(3)
    p1.metric("Spinny Assured Price", f"₹{price:,}")
    if pricing.get("market_price"):
        p2.metric("Comparable Market Price", f"₹{pricing['market_price']:,}")
        p3.metric("You Save", f"₹{pricing['savings_vs_market']:,}")

    st.divider()
    st.subheader("Your ownership assumptions")
    left, right = st.columns(2)

    with left:
        st.markdown("**Payment**")
        payment_mode = st.radio("How will you pay?", ["Loan (EMI)", "Full cash"], horizontal=True)
        if payment_mode == "Loan (EMI)":
            default_loan = finance_d.get("loan_amount_best") or int(price * 0.8)
            loan_amount = st.number_input(
                "Loan amount (₹)",
                min_value=0,
                max_value=price if price else 10_000_000,
                value=min(int(default_loan), price) if price else int(default_loan),
                step=5000,
            )
            down_payment = price - loan_amount
            st.caption(f"Down payment: ₹{down_payment:,}")
            tenure_years_default = finance_d.get("tenure_years_best") or 3
            tenure_months = st.slider(
                "Loan tenure (months)", 12, 84, int(round(tenure_years_default * 12)), step=6
            )
            roi = st.number_input(
                "Interest rate (% p.a.)",
                min_value=0.0,
                max_value=30.0,
                value=float(finance_d.get("roi_percent") or 13.0),
                step=0.1,
            )
            emi = monthly_emi(loan_amount, roi, tenure_months)
            st.metric("Your EMI", f"₹{emi:,.0f}/month")
            if finance_d.get("emi_quoted"):
                st.caption(
                    f"Spinny quoted EMI for its best-matched offer: "
                    f"₹{finance_d['emi_quoted']:,}/month"
                )
        else:
            loan_amount, down_payment, tenure_months, roi, emi = 0, price, 0, 0.0, 0.0

    with right:
        st.markdown("**Running costs**")
        include_maint = st.checkbox("Include scheduled maintenance/servicing", value=True)
        maint_cost = st.number_input(
            "2-year servicing cost (₹)",
            min_value=0,
            value=int(maintenance.get("service_2yr") or 0),
            step=500,
            disabled=not include_maint,
            help="Spinny's own comprehensive 2-year service package cost for this car, when published.",
        )

        include_rsa = st.checkbox("Include roadside assistance (RSA)", value=False)
        rsa_cost = st.number_input(
            "2-year RSA cost (₹)",
            min_value=0,
            value=int(rsa.get("rsa_2yr") or 0),
            step=100,
            disabled=not include_rsa,
        )

        include_warranty = st.checkbox("Include extended warranty", value=False)
        warranty_options = {k: v for k, v in warranty.items() if v}
        warranty_cost = 0
        if include_warranty:
            if warranty_options:
                tier = st.selectbox("Warranty tier", list(warranty_options.keys()))
                warranty_cost = warranty_options[tier]
            else:
                st.caption("No extended warranty pricing published for this car.")

    st.divider()
    hold_months = st.slider("Ownership period (months)", 12, 36, 24, step=1)

    st.subheader("Assured buyback")
    if buyback["available"]:
        default_amount, matched_month = pick_buyback_value(
            buyback["schedule"], hold_months, price
        )
        if matched_month == hold_months:
            st.success(
                f"Spinny publishes an assured buyback value for this car at "
                f"{matched_month} months: ₹{default_amount:,}."
            )
        else:
            st.success(
                f"Spinny publishes an assured buyback schedule for this car. "
                f"The closest published point to {hold_months} months is "
                f"{matched_month} months (₹{default_amount:,}) — adjust below if needed."
            )
        buyback_amount = st.number_input(
            "Assured buyback amount used in calculation (₹)",
            min_value=0,
            value=default_amount,
            step=1000,
        )
        include_plan_cost = False
        plan_cost = buyback["plan_cost"] or 0
        if plan_cost:
            include_plan_cost = st.checkbox(
                f"Include Spinny's buyback plan enrollment fee (₹{plan_cost:,.0f})",
                value=True,
            )
        with st.expander("Full scraped buyback schedule"):
            st.json(buyback["schedule"])
    else:
        st.warning(
            "Spinny hasn't published an assured buyback figure for this specific "
            "listing — this is common for cars already enrolled from a previous "
            "owner. Enter your own estimate below."
        )
        buyback_pct = st.slider(
            "Estimated buyback value after your ownership period (% of purchase price)",
            0,
            100,
            45,
        )
        buyback_amount = int(price * buyback_pct / 100)
        st.caption(f"Estimated buyback amount: ₹{buyback_amount:,}")
        include_plan_cost = False
        plan_cost = 0

    months_financed = min(hold_months, tenure_months) if tenure_months else 0
    total_emi_paid = emi * months_financed

    total_cost = down_payment + total_emi_paid
    if include_maint:
        total_cost += maint_cost
    if include_rsa:
        total_cost += rsa_cost
    if include_warranty:
        total_cost += warranty_cost
    if include_plan_cost:
        total_cost += plan_cost

    net_cost = total_cost - buyback_amount

    st.divider()
    st.subheader(f"Net {hold_months}-month cost of ownership")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total spent", f"₹{total_cost:,.0f}")
    m2.metric("Assured buyback credit", f"-₹{buyback_amount:,.0f}")
    m3.metric(
        "Net cost of ownership",
        f"₹{net_cost:,.0f}",
        help="Total spent minus the buyback amount you get back",
    )
    st.metric("Effective cost per month", f"₹{net_cost / hold_months:,.0f}")

    if tenure_months and hold_months < tenure_months:
        remaining = remaining_balance(loan_amount, roi, tenure_months, hold_months)
        st.info(
            f"Your loan tenure is {tenure_months} months. If you close the loan at "
            f"month {hold_months} (e.g. to hand the car back for buyback), you'd "
            f"still owe roughly ₹{remaining:,.0f} in outstanding principal — this "
            f"is **not** included in the net cost above, since you aren't required "
            f"to close the loan early."
        )

    chart_labels, chart_values = ["Down payment"], [down_payment]
    if total_emi_paid:
        chart_labels.append(f"EMIs ({months_financed} mo)")
        chart_values.append(total_emi_paid)
    if include_maint and maint_cost:
        chart_labels.append("Maintenance")
        chart_values.append(maint_cost)
    if include_rsa and rsa_cost:
        chart_labels.append("RSA")
        chart_values.append(rsa_cost)
    if include_warranty and warranty_cost:
        chart_labels.append("Extended warranty")
        chart_values.append(warranty_cost)
    if include_plan_cost and plan_cost:
        chart_labels.append("Buyback plan fee")
        chart_values.append(plan_cost)
    chart_labels.append("Buyback credit")
    chart_values.append(-buyback_amount)
    chart_labels.append("Net cost")
    chart_values.append(0)

    measures = ["relative"] * (len(chart_labels) - 1) + ["total"]

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=measures,
            x=chart_labels,
            y=chart_values,
            text=[f"₹{v:,.0f}" if m != "total" else "" for v, m in zip(chart_values, measures)],
            textposition="outside",
            connector={"line": {"color": "#c3c2b7"}},
            increasing={"marker": {"color": "#2a78d6"}},
            decreasing={"marker": {"color": "#0ca30c"}},
            totals={"marker": {"color": "#0b0b0b"}},
        )
    )
    fig.update_layout(
        title=f"{hold_months}-month cost breakdown",
        showlegend=False,
        plot_bgcolor="#fcfcfb",
        paper_bgcolor="#fcfcfb",
        font={"color": "#0b0b0b"},
        yaxis_title="₹",
    )
    st.plotly_chart(fig, width="stretch")

    with st.expander("Raw scraped data"):
        st.json(data)
else:
    st.info("Paste a Spinny car listing URL above and click Analyze.")

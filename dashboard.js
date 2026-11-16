(function () {
  "use strict";
  const cases = JSON.parse(document.getElementById("scenario-data").textContent);
  const $ = id => document.getElementById(id);
  const e = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const copy = value => JSON.parse(JSON.stringify(value));
  let current, result;
  function field(label, attribute, value, placeholder = "") {
    return `<label>${e(label)}<input ${attribute} type="number" min="0" step="0.01" value="${e(value)}" placeholder="${e(placeholder)}"></label>`;
  }
  function renderForm() {
    $("group-form").innerHTML = current.people.map(p => {
      const basket = current.items.filter(i => i.owner === p.id).reduce((s,i) => s + FairCart.cents(i.unit_price)*(i.quantity || 1),0);
      return `<div class="person-form" data-person="${e(p.id)}"><div class="person-head"><input class="name-input" data-name type="text" maxlength="120" aria-label="Person name" value="${e(p.name)}"><button class="quiet" data-remove="${e(p.id)}" aria-label="Remove ${e(p.name)}">Remove</button></div><div class="fields">${field(`Basket (${current.currency})`,"data-basket",FairCart.money(basket))}${field("Maximum payment","data-budget",p.budget)}</div></div>`;
    }).join("") + `<button class="add-button" id="add-person" ${current.people.length>=8?"disabled":""}>+ Add person</button>`;
    $("store-form").innerHTML = `<div class="fields">${field("Shipping per order","id=shipping",current.store.shipping_fee)}${field("Free shipping from","id=threshold",current.store.free_shipping_at==null?"":current.store.free_shipping_at,"No threshold")}</div>`;
    $("coupon-form").innerHTML = current.coupons.map((c,i) => `<div class="coupon" data-coupon="${i}"><div class="coupon-heading"><strong>${e(c.id)}</strong><button class="quiet" data-remove-coupon="${i}">Remove</button></div><div class="fields"><label>Coupon type<select data-kind><option value="fixed" ${c.kind==="fixed"?"selected":""}>Fixed discount</option><option value="percent" ${c.kind==="percent"?"selected":""}>Percent off</option></select></label><label>Available to<select data-owner><option value="">Everyone</option>${current.people.map(p=>`<option value="${e(p.id)}" ${c.owner===p.id?"selected":""}>${e(p.name)}</option>`).join("")}</select></label>${field("Minimum basket","data-minimum",c.min_subtotal)}${field(c.kind==="fixed"?"Discount amount":"Percent off","data-discount",c.kind==="fixed"?c.amount:c.percent_off)}${c.kind==="percent"?field("Maximum discount","data-cap",c.max_discount==null?"":c.max_discount,"No cap"):""}</div></div>`).join("") + `<button class="add-button" id="add-coupon" ${current.coupons.length>=16?"disabled":""}>+ Add coupon</button>`;
    $("topup-owner").innerHTML = current.people.map(p=>`<option value="${e(p.id)}">${e(p.name)}</option>`).join("");
    document.querySelectorAll("[data-remove]").forEach(b=>b.addEventListener("click",()=>mutate(()=>{
      if(current.people.length===1) throw new Error("Keep at least one person.");
      const id=b.dataset.remove;
      current.people=current.people.filter(p=>p.id!==id); current.items=current.items.filter(i=>i.owner!==id); current.coupons=current.coupons.filter(c=>c.owner!==id);
    })));
    $("add-person").addEventListener("click",()=>mutate(()=>{
      let n=1; while(current.people.some(p=>p.id===`person-${n}`))n++;
      const id=`person-${n}`; current.people.push({id,name:`Person ${n}`,budget:"50.00"}); current.items.push({id:`basket-${id}`,owner:id,name:"Basket",unit_price:"20.00",quantity:1});
    }));
    $("add-coupon").addEventListener("click",()=>mutate(()=>{
      let n=1; while(current.coupons.some(c=>c.id===`SAVE${n}`))n++;
      current.coupons.push({id:`SAVE${n}`,kind:"fixed",min_subtotal:"50.00",amount:"5.00",owner:null});
    }));
    document.querySelectorAll("[data-remove-coupon]").forEach(b=>b.addEventListener("click",()=>mutate(()=>current.coupons.splice(Number(b.dataset.removeCoupon),1))));
    document.querySelectorAll("[data-kind]").forEach(select=>select.addEventListener("change",()=>{
      try {current=gather();renderForm();$("input-error").textContent="Inputs changed. Calculate to refresh the plan.";}
      catch(error){$("input-error").textContent=error.message;}
    }));
  }
  function gather() {
    const raw=copy(current);
    raw.people=[...document.querySelectorAll("[data-person]")].map(row=>({id:row.dataset.person,name:row.querySelector("[data-name]").value,budget:row.querySelector("[data-budget]").value}));
    raw.items=[...document.querySelectorAll("[data-person]")].map(row=>({id:`basket-${row.dataset.person}`,owner:row.dataset.person,name:"Basket",unit_price:row.querySelector("[data-basket]").value,quantity:1}));
    raw.store={shipping_fee:$("shipping").value,free_shipping_at:$("threshold").value===""?null:$("threshold").value};
    raw.coupons=[...document.querySelectorAll("[data-coupon]")].map(row=>{
      const kind=row.querySelector("[data-kind]").value;
      const c={id:current.coupons[Number(row.dataset.coupon)].id,kind,owner:row.querySelector("[data-owner]").value||null,min_subtotal:row.querySelector("[data-minimum]").value};
      if(kind==="fixed") c.amount=row.querySelector("[data-discount]").value;
      else {c.percent_off=row.querySelector("[data-discount]").value;const cap=row.querySelector("[data-cap]");if(cap&&cap.value!=="")c.max_discount=cap.value;}
      return c;
    });
    FairCart.normalize(raw);return raw;
  }
  function mutate(action) {
    try{current=gather();action();result=FairCart.solve(current);renderForm();renderResult();$("input-error").textContent="";$("topup-result").innerHTML="";}
    catch(error){$("input-error").textContent=error.message;}
  }
  function renderResult() {
    const r=result,feasible=r.status==="feasible",badEqual=r.people.filter(p=>p.equal_split_breaks_cap),currency=e(r.currency),names=Object.fromEntries(r.people.map(p=>[p.id,p.name]));
    $("result").innerHTML=`<div class="result-header"><div><h2>Your checkout plan</h2><p class="helper">${e(r.title)}</p></div><span class="status ${feasible?"":"bad"}">${feasible?"All limits met":"Budget shortfall"}</span></div>
    <div class="saving-box"><div><div class="label">${feasible?"Recommended checkout":"Cheapest possible checkout"}</div><div class="total"><span class="currency">${currency}</span>${e(r.optimal_total)}</div></div><div class="saving"><span>${feasible?"Group saving":"Potential saving"}</span><strong>${e(r.potential_saving)}</strong><span>${currency} vs. separate purchases</span></div></div>
    <div class="result-strip"><span>Separate purchases<strong>${e(r.solo_total)}</strong></span><span>All in one order<strong>${e(r.all_in_one_total)}</strong></span><span>Recommended orders<strong>${r.order_count}</strong></span></div>
    ${!feasible?`<div class="notice">The cheapest checkout costs ${currency} ${e(r.optimal_total)}, but payment caps cover only ${e(r.available_payment)}. The group needs ${e(r.shortfall)} more to satisfy all limits. No feasible payment allocation exists under these terms.</div>`:badEqual.length?`<div class="notice">An equal split would charge ${e(badEqual.map(p=>p.name).join(", "))} more than their payment limit. FairCart adjusts the shares.</div>`:`<div class="notice good">Every payment stays within the person's budget and best solo price.</div>`}
    <h3 class="subhead">What each person pays</h3><div class="table-wrap"><table><thead><tr><th>Person</th><th>Solo price</th><th>Budget</th><th>Equal split</th><th>FairCart</th><th>Saving</th></tr></thead><tbody>${r.people.map(p=>`<tr><td>${e(p.name)}</td><td>${e(p.solo_cost)}</td><td>${e(p.budget)}</td><td style="color:${p.equal_split_breaks_cap?"var(--red)":"var(--muted)"}">${e(p.equal_split)}${p.equal_split_breaks_cap?" *":""}</td><td class="pay">${p.payment===null?"—":e(p.payment)}</td><td class="save-cell">${p.saving===null?"—":e(p.saving)}</td></tr>`).join("")}</tbody></table></div>
    <p class="helper">${badEqual.length?"* Exceeds the person's budget or solo price. ":""}All amounts in ${currency}.</p>
    ${feasible?r.people.map(p=>`<div class="bar-row"><div class="bar-label"><span>${e(p.name)}'s payment</span><span>${e(p.payment)} of ${e(p.solo_cost)} solo price</span></div><div class="bar-track"><div class="bar-fill" style="width:${FairCart.cents(p.solo_cost)?FairCart.cents(p.payment)/FairCart.cents(p.solo_cost)*100:0}%"></div></div></div>`).join(""):""}
    <h3 class="subhead">How to place the orders</h3>${r.orders.map((o,i)=>`<div class="order"><div class="order-top"><span>Order ${i+1}: ${e(o.members.map(id=>names[id]).join(" + "))}</span><span>${currency} ${e(o.total)}</span></div><div class="order-details">Basket ${e(o.subtotal)} · discount ${e(o.discount)} · shipping ${e(o.shipping)} · coupon ${e(o.coupon||"none")}</div></div>`).join("")}
    ${feasible?`<div class="checks"><span>✓ Within every budget</span><span>✓ No one pays more than solo</span><span>✓ Payments add up exactly</span></div>`:""}
    <p class="model-note">Coupons apply to merchandise. Shipping thresholds use the basket total before discounts. Personal coupons require the owner's basket. Public coupons can repeat across orders. Payments settle across the whole group.</p>`;
  }
  function calculate() {
    try{const next=gather(),nextResult=FairCart.solve(next);current=next;result=nextResult;renderResult();$("input-error").textContent="";$("topup-result").innerHTML="";return true;}
    catch(error){$("input-error").textContent=error.message;return false;}
  }
  function checkTopup() {
    if(!calculate())return;
    try{
      const r=FairCart.topup(current,$("topup-owner").value,$("topup-price").value),positive=r.verdict==="costs_more",amount=r.cash_change.replace(/^-/ ,"");
      const headline=positive?`This top-up costs ${r.currency} ${amount} more.`:r.verdict==="saves_cash"?`This top-up saves ${r.currency} ${amount} in cash.`:"This top-up leaves the cash total unchanged.";
      $("topup-result").innerHTML=`<div class="topup-verdict" style="color:${positive?"var(--red)":"var(--green)"}">${e(headline)}</div><div class="topup-breakdown"><span>Without extra item: <b>${e(r.before_total)}</b></span><span>With extra item: <b>${e(r.after_total)}</b></span></div><p>${r.after_budget_feasible?"The expanded basket can satisfy the payment limits.":"The expanded basket cannot satisfy all payment limits."} The comparison measures cash outlay. The extra item's usefulness is a separate decision.</p>`;
    }catch(error){$("topup-result").textContent=error.message;}
  }
  function resetInputs() {
    current=copy(cases[0].cart);result=cases[0].result;
    renderForm();renderResult();$("input-error").textContent="";$("topup-result").innerHTML="";
  }
  $("calculate").addEventListener("click",calculate);$("reset").addEventListener("click",resetInputs);$("topup-check").addEventListener("click",checkTopup);
  document.querySelector(".inputs").addEventListener("input",()=>{$("input-error").textContent="Inputs changed. Calculate to refresh the plan.";});
  resetInputs();
})();

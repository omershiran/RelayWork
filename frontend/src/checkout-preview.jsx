import React, {useState} from "react";
import {Link} from "react-router-dom";

const content = {
  en:{title:"Checkout preview", why:"The payment provider is pending. Try the Sandbox with a sample order.",
      amount:"Sample order total", pay:"Simulate payment", complete:"Sandbox payment confirmed.",
      safety:"No money is charged. This preview does not update any order.", back:"Back to marketplace"},
  he:{title:"תצוגה מקדימה של תשלום", why:"חיבור ספק סליקה עדיין בהמתנה. אפשר לנסות תשלום Sandbox להזמנה לדוגמה.",
      amount:"סכום הזמנה לדוגמה", pay:"הדמיית תשלום", complete:"תשלום ההדגמה אושר.",
      safety:"לא מתבצע חיוב וההדגמה אינה מעדכנת הזמנות.", back:"חזרה לשוק השירותים"}
};

export function CheckoutPreview({lang}) {
  const [confirmed, setConfirmed] = useState(false);
  const t = content[lang];
  return <section className="wrap body narrow">
    <p><Link to="/">{t.back}</Link></p>
    <h1>{t.title}</h1><p>{t.why}</p>
    <article className="card">
      <p>{t.amount} · {new Intl.NumberFormat(lang, {style:"currency", currency:"USD"}).format(25)}</p>
      {confirmed ? <p role="status">{t.complete}</p> : <button onClick={() => setConfirmed(true)}>{t.pay}</button>}
      <p>{t.safety}</p>
    </article>
  </section>;
}

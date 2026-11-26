import React, {useEffect, useState} from "react";
import {Link} from "react-router-dom";
import {Field, api, useAction} from "./shared";
import {Contact} from "./messaging";

function WorkForm({t, refresh}) {
  const action = useAction(t);
  return <form className="card" onSubmit={event => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    for (const name of ["due_at", "expires_at"]) data[name] = new Date(data[name]).toISOString();
    for (const name of ["min_price_cents", "max_price_cents"]) data[name] = data[name] === "" ? null : Number(data[name]);
    action.run(async () => {
      await api("/work-requests", "POST", data);
      form.reset();
      await refresh();
    }, t.workPublished);
  }}>
    <Field name="title" label={t.workTitle} required minLength={2} maxLength={120}/>
    <Field name="category" label={t.category} required minLength={2} maxLength={80}/>
    <label>{t.description}<textarea name="description" required minLength={4} maxLength={6000}/></label>
    <Field name="deliverable" label={t.deliverable} required minLength={2} maxLength={120}/>
    <Field name="country" label={t.country} pattern="[A-Z]{2}"/>
    <Field name="due_at" label={t.due} type="datetime-local" required/>
    <Field name="expires_at" label={t.expires} type="datetime-local" required/>
    <Field name="min_price_cents" label={t.minimum} type="number" min="0" max="100000000"/>
    <Field name="max_price_cents" label={t.maximum} type="number" min="0" max="100000000"/>
    <small>{t.optionalBudget}</small><button disabled={action.busy}>{t.postWork}</button>
    {action.status}
  </form>;
}

export function WorkRequests({t, lang, user}) {
  const [rows, setRows] = useState([]);
  const [mine, setMine] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const action = useAction(t);
  const myView = Boolean(mine && user?.verified);
  const refresh = async () => setRows(await api("/work-requests" + (myView ? "/mine" : "")));
  useEffect(() => { action.run(refresh); }, [myView]);
  const date = new Intl.DateTimeFormat(lang, {dateStyle:"medium", timeStyle:"short"});
  const dollars = new Intl.NumberFormat(lang, {style:"currency", currency:"USD"});
  return <section className="wrap body">
    <h1>{t.work}</h1>
    {user?.verified ? <div className="actions">
      <button onClick={() => setShowForm(!showForm)}>{t.postWork}</button>
      <button className="secondary" onClick={() => setMine(!mine)}>{myView ? t.work : t.myWork}</button>
    </div> : <p><Link to="/account">{t.signInWork}</Link></p>}
    {showForm && user?.verified && <WorkForm t={t} refresh={refresh}/>}
    {action.status}
    {action.busy ? <p role="status">{t.loading}</p> : rows.length === 0 && <p className="empty">{t.none}</p>}
    <div className="grid editors">{rows.map(row => {
      const expired = Date.parse(row.expires_at) <= Date.now();
      return <article className="card" key={row.id}>
        <span className="category">{row.category}</span><h3>{row.title}</h3>
        <p>{row.description}</p><p>{t.deliverable} · {row.deliverable}</p>
        <p>{t.due} · {date.format(new Date(row.due_at))}</p>
        {row.min_price_cents !== null && <p>{t.minimum} · {dollars.format(row.min_price_cents / 100)}</p>}
        {row.max_price_cents !== null && <p>{t.maximum} · {dollars.format(row.max_price_cents / 100)}</p>}
        {user?.verified && !myView && <Contact t={t} kind="work" resourceId={row.id}/>}
        {row.closed_at ? <p>{t.closed}</p> : expired ? <p>{t.expired}</p> : myView &&
          <button className="secondary" disabled={action.busy} onClick={() => action.run(async () => {
            await api("/work-requests/" + row.id + "/close", "POST");
            await refresh();
          }, t.workClosed)}>{t.close}</button>}
      </article>;
    })}</div>
  </section>;
}

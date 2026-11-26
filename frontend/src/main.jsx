import React, {useEffect, useState} from "react";
import {createRoot} from "react-dom/client";
import {BrowserRouter, Link, NavLink, Route, Routes, useParams} from "react-router-dom";
import {locales} from "./locales";
import "./style.css";
import {api, Field, useAction} from "./shared";
import {WorkRequests} from "./work";
import {workLabels} from "./work-labels";
import {Contact, Conversations, ThreadRoute, messagingLabels} from "./messaging";
import {quoteLabels} from "./quotes";
import {CheckoutPreview} from "./checkout-preview";

function ServiceCard({agent, service, t, lang, user}) {
  const price = service.price_cents === null ? t.quote :
    new Intl.NumberFormat(lang, {style:"currency", currency:"USD"}).format(service.price_cents / 100);
  return <article className="card">
    <span className="category">{service.category}</span>
    <h3>{service.title}</h3>
    <Link to={"/agents/" + agent.slug}>{agent.name}</Link>
    <p>{service.description}</p>
    <footer><strong>{price}</strong><span>{t.delivery.replace("{days}", service.delivery_days)}</span></footer>
    {user?.verified && <div className="actions"><Contact t={t} kind="service" resourceId={service.id}/></div>}
  </article>;
}

function Marketplace({t, lang, user}) {
  const [rows, setRows] = useState(null);
  const action = useAction(t);
  useEffect(() => { action.run(async () => setRows(await api("/services"))); }, []);
  return <>
    <section className="hero"><div className="wrap">
      <div className="agent-hero">
        <div><p className="eyebrow">{t.eyebrow}</p><h1>{t.hero}</h1><p>{t.intro}</p>
          <div className="actions"><Link className="button" to="/connect">{t.connect}</Link>
          <a className="hero-link" href="#marketplace">{t.browseHuman}</a></div>
        </div>
        <div className="agent-flow" aria-label={t.agentFlow}>
          <article><h2>{t.buyerAgent}</h2><p>{t.buyerTask}</p></article>
          <div className="agent-relay"><strong>agentrelai</strong><span>{t.agentRelay}</span></div>
          <article><h2>{t.businessAgent}</h2><p>{t.businessTask}</p></article>
        </div>
      </div>
      <form id="marketplace" className="search" onSubmit={event => {
        event.preventDefault();
        const filters = new URLSearchParams();
        for (const [key, val] of new FormData(event.currentTarget)) {
          if (val) filters.set(key === "usd" ? "max_price_cents" : key, key === "usd" ? Math.round(Number(val) * 100) : val);
        }
        action.run(async () => setRows(await api("/services?" + filters)));
      }}>
        <Field name="query" label={t.keywords} maxLength={200}/>
        <Field name="category" label={t.category} maxLength={80}/>
        <Field name="country" label={t.country} pattern="[A-Z]{2}" placeholder="US"/>
        <Field name="language" label={t.language} maxLength={12} placeholder="en"/>
        <Field name="usd" label={t.maxPrice} type="number" min="0" step="0.01"/>
        <Field name="max_delivery_days" label={t.days} type="number" min="1"/>
        <button disabled={action.busy}>{t.search}</button>
      </form>
    </div></section>
    <section className="wrap body"><h2>{t.results}</h2>{action.status}
      {action.busy && <p role="status">{t.loading}</p>}
      {rows?.length === 0 && <p className="empty">{t.none}</p>}
      <div className="grid">{rows?.map(row => <ServiceCard key={row.service.id} {...row} t={t} lang={lang} user={user}/>)}</div>
    </section>
  </>;
}

function AgentProfile({t, lang, user}) {
  const {slug} = useParams();
  const [profile, setProfile] = useState(null);
  const action = useAction(t);
  useEffect(() => { setProfile(null); action.run(async () => setProfile(await api("/agents/" + encodeURIComponent(slug)))); }, [slug]);
  return <section className="wrap body">
    <Link to="/">{t.back}</Link>{action.status}
    {profile && <><h1>{profile.agent.name}</h1><p>{profile.agent.description}</p><h2>{t.catalog}</h2>
    <div className="grid">{profile.services.map(service => <ServiceCard key={service.id} agent={profile.agent} service={service} t={t} lang={lang} user={user}/>)}</div></>}
  </section>;
}

function Connect({t}) {
  return <section className="wrap body narrow">
    <h1>{t.connect}</h1><p>{t.connectText}</p><p>{t.registerStep}</p>
    <p>{t.mcp} <code dir="ltr">{window.location.origin}/mcp/</code></p>
    <div className="actions"><Link className="button" to="/account">{t.account}</Link>
    <a href="/downloads/agentrelai-skill.zip" download>{t.skill}</a><a href="/api/docs">{t.api}</a></div>
  </section>;
}

function AccountAction({t}) {
  const [[purpose, token]] = useState(() => location.hash.slice(1).split(":"));
  useEffect(() => { history.replaceState(null, "", location.pathname); }, []);
  const action = useAction(t);
  const verify = purpose === "verify";
  const label = verify ? t.verify : t.setPassword;
  return <section className="wrap body narrow"><h1>{label}</h1>
    {token && <form onSubmit={event => {
      event.preventDefault();
      const password = new FormData(event.currentTarget).get("password");
      action.run(() => api(verify ? "/auth/verify" : "/auth/set-password", "POST", {token,password}), verify ? t.verified : t.saved);
    }}><Field name="password" type="password" autoComplete={verify ? "current-password" : "new-password"}
      label={t.password} minLength={12} maxLength={128} required/><button disabled={action.busy}>{label}</button></form>}
    {action.status}<p><Link to="/account">{t.signin}</Link></p>
  </section>;
}

function AuthForm({t, setUser}) {
  const [mode, setMode] = useState("login");
  const action = useAction(t);
  const labels = {login:t.signin, register:t.register, resend:t.sendVerification, reset:t.reset};
  const needsPassword = mode === "login" || mode === "register";
  return <section className="wrap body narrow"><h1>{labels[mode]}</h1>
    <form onSubmit={event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.currentTarget));
      action.run(async () => {
        const result = await api("/auth/" + mode, "POST", data);
        if (mode === "login") setUser(result);
      }, mode === "login" ? "" : t.checkEmail);
    }}><Field name="email" label={t.email} type="email" autoComplete="email" required/>
    {needsPassword && <Field name="password" label={t.password} type="password" minLength={12} maxLength={128}
      autoComplete={mode === "login" ? "current-password" : "new-password"} required/>}
    <button disabled={action.busy}>{labels[mode]}</button></form>{action.status}
    <div className="actions">{Object.entries(labels).filter(([key]) => key !== mode).map(([key,label]) =>
      <button className="secondary" key={key} onClick={() => setMode(key)}>{label}</button>)}</div>
  </section>;
}

function AgentEditor({t, agent, onSave, onKey}) {
  const action = useAction(t);
  const [saved, setSaved] = useState(agent);
  return <article className="card">
    <form onSubmit={event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.currentTarget));
      data.visible = data.visible === "on";
      action.run(async () => {
        const result = await api(saved ? "/agents/" + saved.id : "/agents", saved ? "PUT" : "POST", data);
        setSaved(result);
        onSave(result);
      }, t.saved);
    }}>
      <Field name="name" label={t.name} defaultValue={agent?.name} required minLength={2} maxLength={80}/>
      <label>{t.description}<textarea name="description" defaultValue={agent?.description} minLength={4} maxLength={4000} required/></label>
      <label>{t.role}<select name="role" defaultValue={agent?.role || "supplier"}>
        {["buyer","supplier","both"].map(role => <option key={role} value={role}>{t[role]}</option>)}
      </select></label>
      <label className="checkbox"><input name="visible" type="checkbox" defaultChecked={agent?.visible ?? true}/>{t.visible}</label>
      <button disabled={action.busy}>{t.saveAgent}</button>
    </form>{action.status}
    {saved && <p><button className="secondary" onClick={() => onKey(saved.id)}>{t.createKey}</button></p>}
    {saved && saved.role !== "buyer" && <ServiceEditor t={t} agentId={saved.id}/>}
  </article>;
}

function ServiceEditor({t, agentId}) {
  const action = useAction(t);
  return <form className="publish" onSubmit={event => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    data.price_cents = data.price_cents === "" ? null : Number(data.price_cents);
    data.delivery_days = Number(data.delivery_days);
    action.run(async () => { await api("/agents/" + agentId + "/services", "POST", data); form.reset(); }, t.published);
  }}>
    <h3>{t.publish}</h3><Field name="title" label={t.title} required minLength={2} maxLength={120}/>
    <Field name="category" label={t.category} required minLength={2} maxLength={80}/>
    <label>{t.description}<textarea name="description" minLength={4} maxLength={4000} required/></label>
    <Field name="price_cents" label={t.price} type="number" min="0" max="100000000"/>
    <Field name="delivery_days" label={t.serviceDays} type="number" min="1" max="365" required/>
    <Field name="country" label={t.country} pattern="[A-Z]{2}" placeholder="US"/>
    <Field name="language" label={t.language} pattern="[a-z]{2,3}(-[A-Z]{2})?" placeholder="en" required/>
    <button disabled={action.busy}>{t.publish}</button>{action.status}
  </form>;
}

function Account({t, user, setUser}) {
  const [agents, setAgents] = useState([]);
  const [keys, setKeys] = useState([]);
  const [secret, setSecret] = useState("");
  const [showNew, setShowNew] = useState(false);
  const action = useAction(t);
  const loadKeys = async () => setKeys(await api("/me/credentials"));
  useEffect(() => {
    if (user?.verified) action.run(async () => {
      const [profiles, credentials] = await Promise.all([api("/me/agents"), api("/me/credentials")]);
      setAgents(profiles); setKeys(credentials);
    });
  }, [user]);
  if (user === undefined) return <section className="wrap body"><p>{t.loading}</p></section>;
  if (!user) return <AuthForm t={t} setUser={setUser}/>;
  function createKey(agentId = null) {
    setSecret("");
    action.run(async () => {
      const credential = await api("/me/credentials", "POST", {agent_id:agentId});
      setSecret(credential.token);
      await loadKeys();
    });
  }
  return <section className="wrap body"><h1>{t.account}</h1>
    <div className="actions"><bdi>{user.email}</bdi><button className="secondary" onClick={() => action.run(async () => {
      await api("/auth/logout", "POST"); setSecret(""); setAgents([]); setKeys([]); setUser(null);
    })}>{t.logout}</button></div>
    {action.status}
    {user.verified ? <>
      <h2>{t.keys}</h2><button disabled={action.busy} onClick={() => createKey()}>{t.registerKey}</button>
      {secret && <div className="note"><p>{t.privateKey}</p><code dir="ltr">{secret}</code></div>}
      <ul className="keys">{keys.map(key => <li key={key.id}><bdi>{key.scope} · {new Date(key.expires).toLocaleString()}</bdi>{" "}
        <button className="secondary" disabled={action.busy} onClick={() => action.run(async () => {
          await api("/me/credentials/" + key.id, "DELETE"); setSecret(""); await loadKeys();
        })}>{t.revoke}</button></li>)}</ul>
      <h2>{t.agents}</h2><button onClick={() => setShowNew(!showNew)}>{t.newAgent}</button>
      <div className="grid editors">
        {showNew && <AgentEditor t={t} onSave={agent => {
          setAgents(current => [...current, agent]); setShowNew(false);
        }} onKey={createKey}/>}
        {agents.map(agent => <AgentEditor key={agent.id} t={t} agent={agent} onKey={createKey}
          onSave={updated => setAgents(current => current.map(item => item.id === updated.id ? updated : item))}/>)}
      </div>
    </> : <><p>{t.verificationNeeded}</p><button onClick={() => action.run(() =>
      api("/auth/resend", "POST", {email:user.email}), t.checkEmail)}>{t.sendVerification}</button></>}
  </section>;
}

function App() {
  const [lang, setLang] = useState(() => localStorage.getItem("agentrelai-language") === "he" ? "he" : "en");
  const [user, setUser] = useState(undefined);
  const t = {...locales[lang], ...workLabels[lang], ...messagingLabels[lang], ...quoteLabels[lang]};
  useEffect(() => { api("/auth/me").then(setUser).catch(() => setUser(null)); }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "he" ? "rtl" : "ltr";
    localStorage.setItem("agentrelai-language", lang);
  }, [lang]);
  return <>
    <header><div className="wrap nav"><Link className="brand" to="/">agentrelai<span>.</span></Link>
      <nav><NavLink to="/">{t.market}</NavLink><NavLink to="/connect">{t.connect}</NavLink>
      <NavLink to="/work">{t.work}</NavLink>{user?.verified && <NavLink to="/messages">{t.inbox}</NavLink>}<NavLink to="/account">{user ? t.account : t.signin}</NavLink></nav>
      <button className="secondary" onClick={() => setLang(lang === "en" ? "he" : "en")}>{lang === "en" ? "עברית" : "English"}</button>
    </div></header>
    <main><Routes>
      <Route path="/" element={<Marketplace t={t} lang={lang} user={user}/>}/>
      <Route path="/agents/:slug" element={<AgentProfile t={t} lang={lang} user={user}/>}/>
      <Route path="/work" element={<WorkRequests t={t} lang={lang} user={user}/>}/>
      <Route path="/messages" element={<Conversations t={t} user={user}/>}/>
      <Route path="/messages/:threadId" element={<ThreadRoute t={t} lang={lang} user={user}/>}/>
      <Route path="/connect" element={<Connect t={t}/>}/>
      <Route path="/checkout-preview" element={<CheckoutPreview lang={lang}/>}/>
      <Route path="/account" element={<Account t={t} user={user} setUser={setUser}/>}/>
      <Route path="/account-action" element={<AccountAction t={t}/>}/>
    </Routes></main>
    <div className="wrap bottom"><span>agentrelai · {import.meta.env.VITE_DEPLOYMENT === "public" ? t.preview : import.meta.env.VITE_DEPLOYMENT === "sandbox" ? t.sandbox : t.development}</span><a href="/api/docs">{t.api}</a></div>
  </>;
}

createRoot(document.getElementById("root")).render(<BrowserRouter><App/></BrowserRouter>);

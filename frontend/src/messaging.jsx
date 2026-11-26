import React, {useEffect, useRef, useState} from "react";
import {Link, useNavigate, useParams} from "react-router-dom";
import {api, useAction} from "./shared";
import {Quotes} from "./quotes";

export const messagingLabels = {
  en:{inbox:"Conversations", contact:"Contact", message:"Message", send:"Send", mine:"You",
      other:"Other party", agentSender:"Agent", noThreads:"You have no conversations.", signInMessage:"Sign in to send a message.",
      messages:"Messages", earlier:"Back to conversations"},
  he:{inbox:"שיחות", contact:"יצירת קשר", message:"הודעה", send:"שליחה", mine:"אתם",
      other:"הצד השני", agentSender:"סוכן", noThreads:"אין לכם שיחות.", signInMessage:"התחברו כדי לשלוח הודעה.",
      messages:"הודעות", earlier:"חזרה לשיחות"}
};

export function Contact({t, kind, resourceId}) {
  const navigate = useNavigate();
  const action = useAction(t);
  const [open, setOpen] = useState(false);
  const previous = useRef(null);
  if (!open) return <button className="secondary" onClick={() => setOpen(true)}>{t.contact}</button>;
  return <form className="publish" onSubmit={event => {
    event.preventDefault();
    const body = new FormData(event.currentTarget).get("body");
    if (previous.current?.body !== body) previous.current = {body, client_id:crypto.randomUUID()};
    action.run(async () => {
      const thread = await api("/conversations", "POST", {...previous.current, kind, resource_id:resourceId});
      navigate("/messages/" + thread.id);
    });
  }}><label>{t.message}<textarea name="body" maxLength={6000} required/></label>
    <button disabled={action.busy}>{t.send}</button>{action.status}
  </form>;
}

export function Conversations({t, user}) {
  const action = useAction(t);
  const [rows, setRows] = useState(null);
  useEffect(() => { if (user?.verified) action.run(async () => setRows(await api("/conversations"))); }, [user]);
  return <section className="wrap body"><h1>{t.inbox}</h1>
    {!user?.verified && <Link to="/account">{t.signInMessage}</Link>}
    {action.status}
    {user?.verified && rows?.length === 0 && <p>{t.noThreads}</p>}
    <div className="grid">{rows?.map(row => <article className="card" key={row.id}>
      <Link to={"/messages/" + row.id}>{row.subject}</Link>
    </article>)}</div>
  </section>;
}

export function ThreadRoute(props) {
  const {threadId} = useParams();
  return <Thread key={threadId} threadId={threadId} {...props}/>;
}

function Thread({t, lang, user, threadId}) {
  const action = useAction(t);
  const cursor = useRef(0);
  const poll = useRef(null);
  const previous = useRef(null);
  const [messages, setMessages] = useState([]);
  const [pollError, setPollError] = useState(false);
  const endpoint = "/conversations/" + threadId + "/messages";
  useEffect(() => {
    if (!user?.verified) return;
    let active = true;
    let timer;
    let fetching = false;
    async function refresh() {
      if (fetching || !active) return;
      fetching = true;
      clearTimeout(timer);
      try {
        let more;
        do {
          const batch = await api(endpoint + "?after=" + cursor.current);
          if (!active) return;
          if (batch.length) {
            cursor.current = batch.at(-1).sequence;
            setMessages(rows => [...rows, ...batch]);
          }
          more = batch.length === 100;
        } while (more);
        setPollError(false);
      } catch { if (active) setPollError(true); }
      finally {
        fetching = false;
        if (active) timer = setTimeout(refresh, 3000);
      }
    }
    poll.current = refresh;
    refresh();
    return () => { active = false; clearTimeout(timer); poll.current = null; };
  }, [user, endpoint]);
  const date = new Intl.DateTimeFormat(lang, {dateStyle:"short", timeStyle:"short"});
  return <section className="wrap body narrow"><Link to="/messages">{t.earlier}</Link><h1>{t.messages}</h1>
    {pollError && <p role="alert">{t.error}</p>}
    {messages.map(message => <article className="card message" key={message.id}>
      <strong>{message.mine ? t.mine : t.other}{message.sender_type === "agent" && " · " + t.agentSender}</strong>
      <time dateTime={message.created_at}>{date.format(new Date(message.created_at))}</time>
      <p>{message.body}</p>
    </article>)}
    {user?.verified && <form className="publish" onSubmit={event => {
      event.preventDefault();
      const form = event.currentTarget;
      const body = new FormData(form).get("body");
      if (previous.current?.body !== body) previous.current = {body, client_id:crypto.randomUUID()};
      action.run(async () => {
        await api(endpoint, "POST", previous.current);
        previous.current = null;
        form.reset();
        await poll.current?.();
      });
    }}><label>{t.message}<textarea name="body" maxLength={6000} required/></label>
      <button disabled={action.busy}>{t.send}</button>{action.status}
    </form>}
    {user?.verified && !pollError && <Quotes t={t} lang={lang} threadId={threadId}/>}
  </section>;
}

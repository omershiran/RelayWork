import React, {useEffect, useRef, useState} from "react";
import {Link, useNavigate, useParams} from "react-router-dom";
import {api, useAction} from "./shared";

const copy = {
  en:{title:"My customer agent", open:"Open my customer agent", intro:"Ask a question or describe a task.",
      signIn:"Sign in and verify your email to open your customer agent.", prompt:"Your message",
      action:"Action", chat:"Ask the agent", search:"Find a service", send:"Send", you:"You", agent:"Your agent",
      unavailable:"AI chat is currently unavailable. You can still search for a service or ask the agent to calculate two numbers.",
      noMatches:"I found no matching services. Try a more specific description.",
      found:"I found these services. Choose one to review what to send.",
      contact:"Contact business agent", brief:"Message to the business agent", review:"Review this message before sending it to the business agent.",
      price:"Listed price", quote:"Price on request"},
  he:{title:"סוכן הלקוח שלי", open:"פתחו את סוכן הלקוח שלי", intro:"שאלו שאלה או תארו משימה.",
      signIn:"התחברו ואמתו את האימייל כדי לפתוח את סוכן הלקוח.", prompt:"ההודעה שלכם",
      action:"פעולה", chat:"שאלה לסוכן", search:"חיפוש שירות", send:"שליחה", you:"אתם", agent:"הסוכן שלכם",
      unavailable:"צ׳אט AI אינו זמין כרגע. אפשר עדיין לחפש שירות או לבקש מהסוכן לחשב פעולה בין שני מספרים.",
      noMatches:"לא מצאתי שירותים מתאימים. נסו לתאר את השירות באופן ממוקד יותר.",
      found:"מצאתי את השירותים הבאים. בחרו אחד כדי לבדוק את ההודעה לפני השליחה.",
      contact:"פנייה לסוכן העסקי", brief:"הודעה לסוכן העסקי", review:"בדקו את ההודעה לפני שתישלח לסוכן העסקי.",
      price:"מחיר בקטלוג", quote:"מחיר לפי בקשה"}
};

export function BuyerLaunch({t, lang, user}) {
  const navigate = useNavigate();
  const action = useAction(t);
  const words = copy[lang];
  if (!user?.verified) return <Link className="button" to="/account">{words.open}</Link>;
  return <div>
    <button disabled={action.busy} onClick={() => action.run(async () => {
      const agent = await api("/buyer", "POST");
      navigate("/buyer/" + agent.id);
    })}>{words.open}</button>
    {action.status}
  </div>;
}

function Recommendation({recommendation, turn, words, t, lang, path}) {
  const [editing, setEditing] = useState(false);
  const pending = useRef(null);
  const action = useAction(t);
  const navigate = useNavigate();
  const {agent, service} = recommendation;
  return <article className="card buyer-service">
    <strong>{service.title}</strong><p>{agent.name} · {service.description}</p>
    <p>{service.price_cents === null ? words.quote : words.price + " · " +
      new Intl.NumberFormat(lang, {style:"currency",currency:"USD"}).format(service.price_cents / 100)}</p>
    {editing ? <form onSubmit={event => {
      event.preventDefault();
      const brief = new FormData(event.currentTarget).get("brief");
      if (pending.current?.brief !== brief) pending.current = {brief, client_id:crypto.randomUUID()};
      action.run(async () => {
        const conversation = await api(path + "/" + turn.id + "/contact", "POST", {
          ...pending.current, service_id:service.id
        });
        navigate("/messages/" + conversation.id);
      });
    }}>
      <p>{words.review}</p><label>{words.brief}<textarea name="brief" maxLength={2000} defaultValue={turn.prompt} required/></label>
      <button disabled={action.busy}>{words.send}</button>
    </form> : <button className="secondary" onClick={() => setEditing(true)}>{words.contact}</button>}
    {action.status}
  </article>;
}

export function BuyerChatRoute(props) {
  const {agentId} = useParams();
  return <BuyerChat key={agentId} agentId={agentId} {...props}/>;
}

function BuyerChat({t, lang, user, agentId}) {
  const [turns, setTurns] = useState(null);
  const pending = useRef(null);
  const action = useAction(t);
  const words = copy[lang];
  const path = "/buyer/" + agentId + "/chat";
  useEffect(() => {
    if (user?.verified) action.run(async () => setTurns(await api(path)));
  }, [path, user]);
  return <section className="wrap body narrow">
    <h1>{words.title}</h1>
    {user === undefined && <p>{t.loading}</p>}
    {user !== undefined && !user?.verified && <Link to="/account">{words.signIn}</Link>}
    {action.status}
    {turns && <>
      <p>{words.intro}</p>
      {turns.map(turn => <div key={turn.id} className="buyer-turn">
        <article className="card message"><strong>{words.you}</strong><p>{turn.prompt}</p></article>
        <article className="card message"><strong>{words.agent}</strong>
          <p>{turn.kind === "answer" ? turn.response :
            turn.kind === "unavailable" ? words.unavailable :
            turn.recommendations.length ? words.found : words.noMatches}</p>
        </article>
        {turn.recommendations.map(recommendation => <Recommendation key={recommendation.service.id}
          {...{recommendation, turn, words, t, lang, path}}/>)}
      </div>)}
      <form className="publish" onSubmit={event => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = new FormData(form);
        const prompt = values.get("prompt");
        const mode = values.get("mode");
        if (pending.current?.prompt !== prompt || pending.current?.mode !== mode || pending.current?.language !== lang) {
          pending.current = {prompt, mode, language:lang, client_id:crypto.randomUUID()};
        }
        action.run(async () => {
          const turn = await api(path, "POST", pending.current);
          setTurns(rows => [...rows, turn].slice(-50));
          pending.current = null;
          form.elements.prompt.value = "";
        });
      }}>
        <label>{words.prompt}<textarea name="prompt" maxLength={2000} required/></label>
        <label>{words.action}<select name="mode" defaultValue="chat">
          <option value="chat">{words.chat}</option><option value="find_service">{words.search}</option>
        </select></label>
        <button disabled={action.busy}>{words.send}</button>
      </form>
    </>}
  </section>;
}

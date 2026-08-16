import os
import json
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string
from google.cloud import bigquery
from groq import Groq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "lazybot7")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

groq_client = Groq(api_key=GROQ_API_KEY)
bq_client = bigquery.Client(project=PROJECT_ID)

SCHEMA_CONTEXT = """You are a personal health data analyst with access to BigQuery tables in `lazybot7.health_analytics`.

EXACT TABLE SCHEMAS (use ONLY these column names):

1. `steps_record_table`
   row_id INT64, start_time INT64 (unix ms), end_time INT64 (unix ms), count INT64 (steps)
   → Daily steps: SUM(count) GROUP BY DATE(TIMESTAMP_MILLIS(start_time))

2. `heart_rate_record_table`
   row_id INT64, start_time INT64 (unix ms), end_time INT64 (unix ms), start_zone_offset INT64
   → Use to JOIN with heart_rate_record_series_table on row_id = parent_key

3. `heart_rate_record_series_table`
   parent_key INT64, beats_per_minute INT64, epoch_millis INT64 (unix ms)
   → Actual BPM readings. Timestamp column is epoch_millis NOT start_time

4. `sleep_session_record_table`
   row_id INT64, start_time INT64 (unix ms), end_time INT64 (unix ms)
   → Sleep duration hours: (end_time - start_time) / 3600000.0

5. `sleep_stages_table`
   parent_key INT64, stage_type INT64, stage_start_time INT64 (unix ms), stage_end_time INT64 (unix ms)
   → stage_type: 1=awake, 4=light, 5=deep, 6=REM
   → Stage duration hours: (stage_end_time - stage_start_time) / 3600000.0
   → Timestamp column is stage_start_time NOT start_time

6. `resting_heart_rate_record_table`
   row_id INT64, time INT64 (unix ms), beats_per_minute INT64
   → Timestamp column is time NOT start_time. Use DATE(TIMESTAMP_MILLIS(time)) for date grouping

7. `exercise_session_record_table`
   row_id INT64, start_time INT64 (unix ms), end_time INT64 (unix ms), exercise_type INT64
   → Duration hours: (end_time - start_time) / 3600000.0

8. `weight_record_table`
   row_id INT64, time INT64 (unix ms), weight FLOAT64 (kg)
   → Timestamp column is time NOT start_time

9. `distance_record_table`
   row_id INT64, start_time INT64 (unix ms), end_time INT64 (unix ms), distance FLOAT64 (meters)

10. `total_calories_burned_record_table`
    row_id INT64, start_time INT64 (unix ms), end_time INT64 (unix ms), energy FLOAT64 (kcal)

11. `active_calories_burned_record_table`
    row_id INT64, start_time INT64 (unix ms), end_time INT64 (unix ms), energy FLOAT64 (kcal)

SQL RULES (strictly follow):
- Always fully qualify tables: `lazybot7.health_analytics.table_name`
- All timestamps are Unix milliseconds. Use TIMESTAMP_MILLIS(column) to convert
- CRITICAL: Each table has different timestamp column names — use the exact names from the schema above
- Group by day: DATE(TIMESTAMP_MILLIS(timestamp_column)) — use the correct column per table
- "This week" = DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
- "This month" = DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
- Always use CTEs (WITH clause) instead of nested subqueries
- Always add LIMIT 100 unless user specifies otherwise
- For deep sleep: filter WHERE stage_type = 5, duration = (stage_end_time - stage_start_time)/3600000.0
- For RHR: use beats_per_minute column, date from TIMESTAMP_MILLIS(time)
- For heart rate BPM readings: use heart_rate_record_series_table, timestamp is epoch_millis
- Return ONLY raw BigQuery Standard SQL — no markdown, no code fences, no explanation — no markdown, no code fences, no explanation"""

ANSWER_SYSTEM = """You are a friendly personal health assistant. The user asked a question about their health data and you have the query results. 

Give a direct, conversational answer in 2-4 sentences. Lead with the key number or insight. Add one brief pattern observation. Keep under 150 words. Plain language only — no SQL or technical terms. If empty results, say so honestly and suggest why."""


def generate_sql(question: str) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SCHEMA_CONTEXT},
            {"role": "user", "content": f"Generate BigQuery SQL to answer: {question}"}
        ],
        temperature=0.1,
        max_tokens=500
    )
    sql = response.choices[0].message.content.strip()
    # Strip any markdown fences if model adds them
    if "```" in sql:
        parts = sql.split("```")
        sql = parts[1] if len(parts) > 1 else sql
        if sql.lower().startswith("sql"):
            sql = sql[3:]
    return sql.strip()


def run_query(sql: str) -> list:
    query_job = bq_client.query(sql)
    rows = query_job.result()
    return [dict(row) for row in rows]


def generate_answer(question: str, results: list) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM},
            {"role": "user", "content": f"Question: {question}\n\nData: {json.dumps(results[:50], default=str)}"}
        ],
        temperature=0.7,
        max_tokens=300
    )
    return response.choices[0].message.content.strip()


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Health AI Assistant</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :root{
      --bg:#0f1117;--surface:#1a1d27;--surface-2:#22263a;
      --border:rgba(255,255,255,0.07);--text:#e8eaf0;--muted:#7b8099;
      --accent:#4f8ef7;--accent-soft:rgba(79,142,247,0.12);
      --green:#34d399;--red:#f87171;--radius:14px;
    }
    body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column}
    header{padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px;background:rgba(26,29,39,0.9);backdrop-filter:blur(12px);position:sticky;top:0;z-index:10}
    .logo{width:36px;height:36px;background:linear-gradient(135deg,#4f8ef7,#34d399);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px}
    header h1{font-size:16px;font-weight:600;letter-spacing:-0.3px}
    header p{font-size:11px;color:var(--muted);margin-top:2px}
    .live{margin-left:auto;display:flex;align-items:center;gap:6px;font-size:12px;color:var(--green)}
    .dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
    @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
    main{flex:1;max-width:720px;width:100%;margin:0 auto;padding:24px 16px 150px;display:flex;flex-direction:column;gap:16px}
    .empty{text-align:center;padding:52px 24px;color:var(--muted)}
    .empty .icon{font-size:52px;margin-bottom:16px}
    .empty h2{font-size:20px;font-weight:600;color:var(--text);margin-bottom:8px}
    .empty p{font-size:14px;line-height:1.6;max-width:380px;margin:0 auto 24px}
    .chips{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
    .chip{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:7px 14px;font-size:13px;color:var(--muted);cursor:pointer;transition:all .18s}
    .chip:hover{background:var(--surface-2);color:var(--text);border-color:var(--accent)}
    .messages{display:flex;flex-direction:column;gap:14px}
    .msg{display:flex;gap:10px;animation:fadeUp .22s ease}
    @keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
    .msg.user{flex-direction:row-reverse}
    .av{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}
    .av.ai{background:linear-gradient(135deg,#4f8ef7,#34d399)}
    .av.user{background:var(--surface-2);border:1px solid var(--border)}
    .bubble{max-width:82%;padding:12px 15px;border-radius:var(--radius);font-size:14px;line-height:1.65}
    .msg.ai .bubble{background:var(--surface);border:1px solid var(--border);border-top-left-radius:4px}
    .msg.user .bubble{background:var(--accent-soft);border:1px solid rgba(79,142,247,0.2);border-top-right-radius:4px}
    .sql-block{margin-top:10px;background:rgba(0,0,0,0.35);border:1px solid var(--border);border-radius:8px;overflow:hidden}
    .sql-head{padding:5px 12px;font-size:10px;color:var(--muted);background:rgba(255,255,255,0.03);text-transform:uppercase;letter-spacing:.5px;display:flex;justify-content:space-between}
    .sql-code{padding:10px 12px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#a5b4fc;white-space:pre-wrap;word-break:break-word;line-height:1.6}
    .thinking{display:flex;gap:5px;align-items:center;padding:4px 0}
    .thinking span{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:bounce 1.2s infinite}
    .thinking span:nth-child(2){animation-delay:.2s}.thinking span:nth-child(3){animation-delay:.4s}
    @keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}
    .input-bar{position:fixed;bottom:0;left:0;right:0;padding:16px;background:linear-gradient(to top,var(--bg) 65%,transparent)}
    .input-wrap{max-width:720px;margin:0 auto;display:flex;gap:10px;align-items:flex-end;background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:10px 12px;transition:border-color .2s}
    .input-wrap:focus-within{border-color:var(--accent)}
    textarea{flex:1;background:transparent;border:none;outline:none;color:var(--text);font-family:'Inter',sans-serif;font-size:14px;resize:none;min-height:24px;max-height:120px;line-height:1.5}
    textarea::placeholder{color:var(--muted)}
    #send{width:36px;height:36px;background:var(--accent);border:none;border-radius:10px;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .18s}
    #send:hover{background:#6aa3ff;transform:scale(1.05)}
    #send:disabled{background:var(--surface-2);cursor:not-allowed;transform:none}
    .err{color:var(--red)}
    .model-badge{font-size:10px;color:var(--muted);margin-top:6px;text-align:right;opacity:.6}
  </style>
</head>
<body>
<header>
  <div class="logo">❤️</div>
  <div><h1>Health AI</h1><p>Llama 3.1 70B · BigQuery · Your personal data</p></div>
  <div class="live"><div class="dot"></div>Live</div>
</header>
<main>
  <div class="empty" id="empty">
    <div class="icon">🧬</div>
    <h2>Ask anything about your health</h2>
    <p>I have access to your complete health history — steps, heart rate, sleep, workouts, calories, and more.</p>
    <div class="chips">
      <span class="chip" onclick="ask(this)">How many steps did I average this week?</span>
      <span class="chip" onclick="ask(this)">What was my resting heart rate trend this month?</span>
      <span class="chip" onclick="ask(this)">How much deep sleep did I get last week?</span>
      <span class="chip" onclick="ask(this)">Which day of the week do I walk most?</span>
      <span class="chip" onclick="ask(this)">Show my step count for the last 7 days</span>
      <span class="chip" onclick="ask(this)">How long do I sleep on average?</span>
      <span class="chip" onclick="ask(this)">What is my peak heart rate during workouts?</span>
      <span class="chip" onclick="ask(this)">How many calories did I burn this week?</span>
    </div>
  </div>
  <div class="messages" id="msgs"></div>
</main>
<div class="input-bar">
  <div class="input-wrap">
    <textarea id="q" rows="1" placeholder="Ask about your health data..." onkeydown="handleKey(event)" oninput="resize(this)"></textarea>
    <button id="send" onclick="send()">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
    </button>
  </div>
</div>
<script>
  const msgs=document.getElementById('msgs'),qEl=document.getElementById('q'),btn=document.getElementById('send'),empty=document.getElementById('empty');
  function resize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,120)+'px'}
  function handleKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}
  function ask(el){qEl.value=el.textContent;send()}
  function addMsg(role,html,sql){
    empty.style.display='none';
    const d=document.createElement('div');d.className='msg '+role;
    const av=role==='ai'?'❤️':'👤';
    const sqlHtml=sql?`<div class="sql-block"><div class="sql-head"><span>Generated SQL</span><span>BigQuery</span></div><div class="sql-code">${escHtml(sql)}</div></div>`:'';
    d.innerHTML=`<div class="av ${role}">${av}</div><div class="bubble">${html}${sqlHtml}</div>`;
    msgs.appendChild(d);d.scrollIntoView({behavior:'smooth',block:'end'});return d;
  }
  function escHtml(t){return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
  function thinking(){
    empty.style.display='none';
    const d=document.createElement('div');d.className='msg ai';
    d.innerHTML=`<div class="av ai">❤️</div><div class="bubble"><div class="thinking"><span></span><span></span><span></span></div></div>`;
    msgs.appendChild(d);d.scrollIntoView({behavior:'smooth',block:'end'});return d;
  }
  async function send(){
    const q=qEl.value.trim();if(!q)return;
    qEl.value='';qEl.style.height='auto';btn.disabled=true;
    addMsg('user',q);
    const t=thinking();
    try{
      const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
      const data=await r.json();t.remove();
      if(data.error)addMsg('ai',`<span class="err">⚠️ ${data.error}</span>`);
      else addMsg('ai',data.answer,data.sql);
    }catch(e){t.remove();addMsg('ai','<span class="err">⚠️ Connection error. Try again.</span>')}
    btn.disabled=false;qEl.focus();
  }
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "model": "llama-3.3-70b-versatile", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    question = (data or {}).get("question", "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400
    logger.info(f"Question: {question}")
    try:
        sql = generate_sql(question)
        logger.info(f"SQL: {sql}")
        results = run_query(sql)
        logger.info(f"Rows: {len(results)}")
        answer = generate_answer(question, results)
        return jsonify({"question": question, "sql": sql, "row_count": len(results), "answer": answer})
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

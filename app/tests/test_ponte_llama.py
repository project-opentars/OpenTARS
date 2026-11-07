"""A tradução da ponte de medida entre a API do Ollama e a do llama-server."""
import ponte_llama as p

corpo = {"model": "m", "think": False, "logprobs": True, "tools": [{"type": "function"}], "options": {"temperature": 0.2, "num_predict": 9}, "messages": [
    {"role": "system", "content": "s"}, {"role": "user", "content": "oi", "images": ["AAA"]},
    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "ls", "arguments": {"a": 1}}}]},
    {"role": "tool", "tool_name": "ls", "content": "ok"}]}
o = p.para_openai(corpo, {"top_k": 20.0, "repeat_penalty": 1.05})
assert o["chat_template_kwargs"] == {"enable_thinking": False} and o["temperature"] == 0.2 and o["top_k"] == 20.0 and o["max_tokens"] == 9
assert o["messages"][1]["content"][1]["image_url"]["url"].endswith("AAA")
chamada = o["messages"][2]["tool_calls"][0]
assert chamada["function"]["arguments"] == '{"a": 1}' and o["messages"][3]["tool_call_id"] == chamada["id"] and o["messages"][3]["name"] == "ls"

r = {"choices": [{"finish_reason": "tool_calls", "logprobs": {"content": [{"token": "a", "logprob": -0.5}]},
                  "message": {"content": None, "tool_calls": [{"function": {"name": "ls", "arguments": '{"a": 1}'}}]}}]}
s = p.para_ollama(r, "m", 0)
assert s["done"] and s["message"]["tool_calls"][0]["function"]["arguments"] == {"a": 1} and s["logprobs"] == [{"token": "a", "logprob": -0.5}]
print("OK: ponte de medida")

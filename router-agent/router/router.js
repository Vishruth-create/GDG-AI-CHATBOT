import {client} from "../llm/client.js";
import {buildRouterPrompt} from "./prompt.js";
import { parseLLMResponse } from "./parser.js";

export async function llmRouter ({message, shortMemory, longMemory}){
  const prompt=buildRouterPrompt({message, shortMemory, longMemory});
  const res = await client.chat.completions.create({
    model:"gpt-4o-mini",
    temperature:0,
    messages:[
      {
        role:"system",
        content: "You are a strict JSON classifier."
      },
      {
        role:"user",
        content:prompt
      }
    ]
  });
  const text = res.choices[0].message.content;

  return parseLLMResponse(text);
  }
}

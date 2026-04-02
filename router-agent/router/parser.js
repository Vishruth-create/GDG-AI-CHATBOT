export function parseLLMResponse(text){
  if(!text){
    return fallback("Empty response");
  }
  try{
    return normalize(JSON.parse(text));
  } catch {}

  const jsonMatch=text.match(/\{[\s\S]*\}/);

  if(jsonMatch){
    try{
      return normalize(JSON.parse(jsonMatch[0]));
    } catch {}
  }
  try{
    const cleaned=text
      .replace(/```json/g, "")
      .replace(/```/g, "")
      .trim();

    return normalize(JSON.parse(cleaned));
  } catch {}

  return fallback("Could not parse LLM response");
}

function normalize(obj){
  const type= obj.type === "FOLLOW_UP" ? "FOLLOW_UP" : "NEW_QUERY";
  const confidence=typeof obj.confidence==="number" ? Math.max(0, Math.min(1, obj.confidence)) : 0.5;
  const reason=typeof obj.reason==="string" ? obj.reason : "No reason provided";
  return {type,confidence,reason};
}

function fallback(reason){
  return {
    type:"NEW_QUERY",
    confidence:0.5,
    reason
  };
}

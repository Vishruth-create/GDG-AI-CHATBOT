import {StateGraph} from "@langchain/langgraph";
import {llmRouter} from "../router/router.js";

const graph = new StateGraph({
  channels: {
    messsage:"string",
    shortMemory:"array",
    longMemory:"string",
    route:"string"
  }
});

graph.addNode("router", async (state)=>{
  const result=await llmRouter(state);
  return {
    t...state,
    route:result.type,
    routeMeta:result
  };
});

graph.addConditionalEdges("router", (state)=>{
  if(state.route==="FOLLOW_UP"){
    return "followUpHandler";
  }
  return "newQueryHandler";
});

graph.addNode("followUpHandler", (state)=>state);
graph.addNode("newQueryHandler", (state)=>state);

graph.setEntryPoint("router");
export const app=graph.complile();

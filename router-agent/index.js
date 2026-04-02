import {app} from "./graph/graph.js";
const input={
  message:"Change it to 6pm",
  shortMemory:["Set reminder at 5pm"],
  longMemory: ""
};

const result=await app.invoke(input);
console.log(result);

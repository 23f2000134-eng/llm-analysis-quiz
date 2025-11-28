import { emailNumber } from "./utils.js";

const code = await emailNumber();
document.querySelector("#question").innerHTML = code
  ? `Secret code is <strong>${code}</strong> and not <em>${code + Math.round(Math.random() * 1000)}</em>.`
  : "Please provide ?email=";

import { render } from "preact";
import { App } from "./App";
import { createApi } from "./api";
import { takeToken } from "./token";
import "./styles.css";

const token = takeToken(location, history);
const root = document.getElementById("app");
if (root) render(<App api={token === null ? null : createApi(token)} />, root);

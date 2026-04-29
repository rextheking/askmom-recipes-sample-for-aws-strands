// Frontend configuration.
//
// After deploying the infra stack, replace API_BASE_URL with your own
// API Gateway URL. You can find it with:
//   cd infra && make outputs
// Look for the ApiUrl row.
//
// See the top-level README.md, step 5 of "Quick start: deploy your own".
window.ASKMOM_CONFIG = {
  API_BASE_URL: "REPLACE_ME_WITH_YOUR_API_GATEWAY_URL",
};

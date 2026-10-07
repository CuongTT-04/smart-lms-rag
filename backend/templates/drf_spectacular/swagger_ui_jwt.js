"use strict";

const swaggerSettings = {{ settings|safe }};
const schemaAuthNames = {{ schema_auth_names|safe }};
let schemaAuthFailed = false;
const plugins = [];

const reloadSchemaOnAuthChange = () => ({
  statePlugins: {
    auth: {
      wrapActions: {
        authorize: (ori) => (...args) => {
          schemaAuthFailed = false;
          setTimeout(() => ui.specActions.download());
          return ori(...args);
        },
        logout: (ori) => (...args) => {
          schemaAuthFailed = false;
          setTimeout(() => ui.specActions.download());
          return ori(...args);
        },
      },
    },
  },
});

if (schemaAuthNames.length > 0) plugins.push(reloadSchemaOnAuthChange);

const responseInterceptor = (response) => {
  if (!response.ok && response.url.endsWith("/api/schema/") && !schemaAuthFailed) {
    schemaAuthFailed = true;
    setTimeout(() => ui.specActions.download());
  }
  return response;
};

const ui = SwaggerUIBundle({
  url: "{{ schema_url|escapejs }}",
  dom_id: "#swagger-ui",
  presets: [SwaggerUIBundle.presets.apis],
  plugins,
  layout: "BaseLayout",
  responseInterceptor,
  ...swaggerSettings,
});

{% if oauth2_config %}ui.initOAuth({{ oauth2_config|safe }});{% endif %}

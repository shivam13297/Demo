import requests
import yaml
from identityNow import handle_identitynow_call
from okta import handle_okta_call
from iiq import handle_iiq_call
from utils import extract_path_params, extract_query_params
import gradio as gr
import os
from dotenv import load_dotenv
from pathlib import Path

script_dir = Path(__file__).resolve().parent
env_path = script_dir / '.env'
load_dotenv(dotenv_path=env_path)

def fetch_api_endpoints_yaml(spec_url):
    try:
        response = requests.get(spec_url)
        response.raise_for_status()
        content = response.text
        api_spec = yaml.safe_load(content)
    except Exception as e:
        print(f"Error fetching/parsing YAML spec from {spec_url}: {e}")
        return {}
    
    endpoints = {}
    if "paths" not in api_spec:
        print("No endpoints found in the specification.")
        return {}
    
    valid_methods = ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']
    for path, methods in api_spec["paths"].items():
        endpoints[path] = {}
        if not methods or not isinstance(methods, dict):
            continue
        
        # Get common parameters defined at path level
        common_params = methods.get("parameters", [])
        
        for method, details in methods.items():
            if method.lower() not in valid_methods:
                continue
            
            # Combine path-level and method-level parameters
            method_params = details.get("parameters", [])
            all_params = common_params + method_params
            
            endpoint_info = {
                "summary": details.get("summary", ""),
                "description": details.get("description", ""),
                "parameters": all_params  # Include all parameters
            }
            endpoints[path][method.lower()] = endpoint_info
    return endpoints

def fetch_api_endpoints_json(spec_url):
    try:
        response = requests.get(spec_url)
        response.raise_for_status()
        api_spec = response.json()
    except Exception as e:
        print(f"Error fetching/parsing JSON spec from {spec_url}: {e}")
        return {}
    
    endpoints = {}
    if "paths" not in api_spec:
        print("No endpoints found in the specification.")
        return {}
    
    valid_methods = ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']
    for path, methods in api_spec["paths"].items():
        endpoints[path] = {}
        if not methods or not isinstance(methods, dict):
            continue
        
        # Get common parameters defined at path level
        common_params = methods.get("parameters", [])
        
        for method, details in methods.items():
            if method.lower() not in valid_methods:
                continue
            
            # Combine path-level and method-level parameters
            method_params = details.get("parameters", [])
            all_params = common_params + method_params
            
            endpoint_info = {
                "summary": details.get("summary", ""),
                "description": details.get("description", ""),
                "parameters": all_params  # Include all parameters
            }
            endpoints[path][method.lower()] = endpoint_info
    return endpoints

def get_endpoints(spec_choice):
    api_spec_options = {
        "Okta (JSON)": os.getenv("OKTA_API_SPEC"),
        "SailPoint IdentityNow (YAML)": os.getenv("IDENTITY_NOW_API_SPEC"),
        "Sailpoint IIQ (YAML)": os.getenv("IIQ_API_SPEC")
    }
    spec_url = api_spec_options.get(spec_choice)
    if not spec_url:
        return {}
    if "JSON" in spec_choice:
        return fetch_api_endpoints_json(spec_url)
    return fetch_api_endpoints_yaml(spec_url)

def group_endpoints(endpoints, spec_choice):
    """Group endpoints with special handling for Okta API"""
    groups = {}
    
    # Special handling for Okta endpoints
    if spec_choice == "Okta (JSON)":
        for path, methods in endpoints.items():
            # Remove /api/v1/ prefix and get the first segment
            clean_path = path.replace('/api/v1/', '')
            segments = clean_path.strip("/").split("/")
            group_key = segments[0] if segments else "other"
            
            if group_key not in groups:
                groups[group_key] = {}
            groups[group_key][path] = methods
    else:
        # Original grouping logic for other APIs
        for path, methods in endpoints.items():
            segments = path.strip("/").split("/")
            group_key = segments[0] if segments[0] != "" else "other"
            if group_key not in groups:
                groups[group_key] = {}
            groups[group_key][path] = methods
    
    return groups

with gr.Blocks(
    theme=gr.themes.Default(
        primary_hue=gr.themes.colors.red,
        secondary_hue=gr.themes.colors.gray,
        neutral_hue="slate",
        text_size="md",
        radius_size="md",
        font=gr.themes.GoogleFont("Inter")
    )
) as demo:
    gr.Markdown("# Data Connector Demo")
    gr.Markdown("Select an API spec, then click Refresh Endpoints to see available endpoints grouped in accordions.")
    
    # Session state
    session_id_state = gr.State("")
    confirmed_endpoints_state = gr.State([])
    display_values_state = gr.State([])
    
    max_groups = 100
    
    # API Spec Selection
    with gr.Row():
        spec_choice = gr.Radio(
            label="Choose API Spec",
            choices=["Okta (JSON)", "SailPoint IdentityNow (YAML)", "Sailpoint IIQ (YAML)"],
            value="SailPoint IdentityNow (YAML)"
        )
        refresh_eps = gr.Button("Refresh Endpoints", variant="primary")
    
    # Loading indicator
    loading_status = gr.Markdown("Select an API spec and click 'Refresh Endpoints' to load available endpoints.")
    
    # Create accordion placeholders
    accordion_placeholders = []
    with gr.Column():
        for i in range(max_groups):
            with gr.Accordion(label="", open=False, visible=False) as acc:
                cb = gr.CheckboxGroup(label="", choices=[], value=[])
            accordion_placeholders.append((acc, cb))
    
    # Parameter group
    with gr.Group(visible=False) as param_group:
        param_header = gr.Markdown("### Parameters Required")  # Default header
        param_components = []
        with gr.Column() as param_container:
            for i in range(5):
                with gr.Group(visible=False) as group:
                    display = gr.Markdown(visible=False)
                    input_box = gr.Textbox(
                        label="Parameter Value",
                        visible=False,
                        interactive=True
                    )
                    param_components.append((group, display, input_box))
    
    # Authentication sections
    with gr.Group() as identitynow_auth:
        with gr.Row():
            grant_type = gr.Textbox(label="Enter grant_type", value="client_credentials")
            client_id = gr.Textbox(label="Enter client_id")
            client_secret = gr.Textbox(label="Enter client_secret", type="password")
    
    with gr.Group(visible=False) as okta_auth:
        api_token = gr.Textbox(label="Enter Okta API Token", type="password")
    
    with gr.Group(visible=False) as iiq_auth:
        with gr.Row():
            iiq_username = gr.Textbox(label="Enter IIQ Username")
            iiq_password = gr.Textbox(label="Enter IIQ Password", type="password")
    
    api_base_url = gr.Textbox(label="Enter API Base URL")
    
    # Buttons
    confirm_endpoints_btn = gr.Button("Submit and Confirm Endpoints", variant="primary")
    call_api_btn = gr.Button("Call API", variant="primary")
    
    # Output components
    responses_out = gr.JSON(label="API Responses")
    download_out = gr.File(label="Download Session Data (ZIP)")

    def update_acc(spec_choice):
        """Update accordions with endpoints"""
        try:
            endpoints = get_endpoints(spec_choice)
            
            if not endpoints:
                return [gr.update(visible=False)] * (max_groups * 2) + ["⚠️ No endpoints found"]
            
            groups = group_endpoints(endpoints, spec_choice)
            group_keys = list(groups.keys())

            if not group_keys:
                return [gr.update(visible=False)] * (max_groups * 2) + ["⚠️ No endpoint groups found"]
                
            updates = []
            
            # Always process exactly max_groups number of slots
            for i in range(max_groups):
                if i < len(group_keys):
                    group = group_keys[i]
                    choices = []
                    # Collect GET endpoints for this group
                    for ep, methods in groups[group].items():
                        if 'get' in methods:
                            summary = methods['get'].get('summary', 'No summary')
                            label = f"{ep} | GET - {summary}"
                            choices.append(label)
                    
                    # Add updates regardless of choices
                    acc_update = gr.update(
                        label=f"Group: {group}" if choices else "",
                        visible=bool(choices),
                        open=(i == 0 and bool(choices))
                    )
                    cb_update = gr.update(choices=choices, value=[], visible=bool(choices))
                    updates.append((acc_update, cb_update))
                else:
                    # Fill remaining slots with hidden updates
                    acc_update = gr.update(visible=False, label="")
                    cb_update = gr.update(visible=False, choices=[], value=[])
                    updates.append((acc_update, cb_update))

            # Flatten updates and add status message
            flattened = []
            for up in updates:
                flattened.extend(up)  # This will give us exactly max_groups * 2 updates
            
            visible_groups = sum(1 for group in groups.values() if any('get' in methods for methods in group.values()))
            success_msg = f"✅ Loaded {visible_groups} groups with GET endpoints"
            flattened.append(success_msg)
            
            return flattened
                
        except Exception as e:
            error_msg = f"❌ Error loading endpoints: {str(e)}"
            return [gr.update(visible=False)] * (max_groups * 2) + [error_msg]
        
    def update_auth_fields(api_choice):
        updates = {
            "Okta (JSON)": [False, True, False],
            "SailPoint IdentityNow (YAML)": [True, False, False],
            "Sailpoint IIQ (YAML)": [False, False, True]
        }
        visibilities = updates.get(api_choice, [False, False, False])
        return [
            gr.update(visible=visibilities[0]),
            gr.update(visible=visibilities[1]),
            gr.update(visible=visibilities[2])
        ]

    def confirm_selected_endpoints(spec_choice, *checkbox_values):
        """Collect and confirm all selected endpoints"""
        all_selected = []
        
        for checkbox_group in checkbox_values:
            if isinstance(checkbox_group, list) and checkbox_group:
                all_selected.extend(checkbox_group)
        
        # Get the API spec
        endpoints = get_endpoints(spec_choice)
        
        # Process selected endpoints to find ones with parameters
        endpoints_with_params = []
        display_values = []  # Track display values
        for selection in all_selected:
            endpoint = selection.split(" | ")[0]
            endpoint_spec = endpoints.get(endpoint, {}).get('get', {})
            
            # Get both path and query parameters
            path_params = extract_path_params(endpoint)
            query_params = extract_query_params(endpoint_spec)
            
            if path_params or query_params:
                endpoints_with_params.append((endpoint, path_params, query_params))
                display_values.append(f"Endpoint: {endpoint}")

        # Create updates for all components
        updates = []
        updates.append(endpoints_with_params)  # confirmed_endpoints_state
        updates.append(display_values)  # display_values_state
        
        # Determine parameter types present
        has_path_params = any(path_params for _, path_params, _ in endpoints_with_params)
        has_query_params = any(query_params for _, _, query_params in endpoints_with_params)
        
        # Set appropriate header based on parameter types
        if has_path_params and has_query_params:
            header_text = "### Path and Query Parameters Required"
        elif has_path_params:
            header_text = "### Path Parameters Required/Optional"
        elif has_query_params:
            header_text = "### Query Parameters Required/Optional"
        else:
            header_text = "### Parameters Required"
        
        # Update group visibility and header text separately
        updates.append(gr.update(visible=bool(endpoints_with_params)))  # param_group visibility
        updates.append(gr.update(value=header_text, visible=True))  # param_header update

        # Then create updates for each parameter component
        param_index = 0
        for i in range(100):  # Assuming max 5 endpoints
            if i < len(endpoints_with_params):
                endpoint, path_params, query_params = endpoints_with_params[i]
                
                # Handle path parameters
                for param_name in path_params:  # Changed: iterate directly over parameter names
                    if param_index < 5:  # Stay within component limit
                        updates.extend([
                            gr.update(visible=True),
                            gr.update(visible=True, value=f"Endpoint: {endpoint} - Path Parameter"),
                            gr.update(
                                visible=True,
                                label=f"Enter path parameter: {param_name}",
                                placeholder=f"Required path parameter for {endpoint}"
                            )
                        ])
                        param_index += 1
                
                # Handle query parameters
                for param in query_params:  # Changed: handle query parameter tuples
                    _, name, required, description = param  # Unpack all 4 values
                    if param_index < 5:  # Stay within component limit
                        updates.extend([
                            gr.update(visible=True),
                            gr.update(visible=True, value=f"Endpoint: {endpoint} - Query Parameter"),
                            gr.update(
                                visible=True,
                                label=f"Enter query parameter: {name}" + (" (Required)" if required else " (Optional)"),
                                placeholder=description
                            )
                        ])
                        param_index += 1

        # Fill remaining parameter components with hidden updates
        while param_index < 5:
            updates.extend([
                gr.update(visible=False),
                gr.update(visible=False, value=""),
                gr.update(visible=False, label="")
            ])
            param_index += 1
        
        return updates
    
    def handle_api_call(spec_choice, api_base_url, session_id, grant_type, client_id, client_secret, 
                   api_token, iiq_username, iiq_password, display_values, *args):
        # Create param_values dictionary
        num_params = len(param_components)
        path_params = {}
        query_params = {}
        
        for i, display_value in enumerate(display_values):
            if display_value and args[i]:
                endpoint_text = display_value.split(": ")[1].split(" - ")[0]
                param_type = "path" if "Path Parameter" in display_value else "query"
                param_name = args[i].split(":")[0].strip()
                
                if param_type == "path":
                    path_params[param_name] = args[i]
                else:
                    query_params[param_name] = args[i]
        
        checkbox_values = args[num_params:]
        
        try:
            if spec_choice == "Okta (JSON)":
                return handle_okta_call(api_base_url, api_token, session_id, path_params, query_params, *checkbox_values)
            elif spec_choice == "SailPoint IdentityNow (YAML)":
                return handle_identitynow_call(api_base_url, grant_type, client_id, client_secret, 
                                        session_id, path_params, query_params, *checkbox_values)
            else:  # IIQ
                return handle_iiq_call(api_base_url, iiq_username, iiq_password, session_id, 
                                path_params, query_params, *checkbox_values)
        except Exception as e:
            print(f"Error in handle_api_call: {str(e)}")
            return (
                {"error": f"API call failed: {str(e)}"},
                None,
                session_id,
                f"❌ Error: {str(e)}"
            )

    # Wire up the events
    spec_choice.change(
        fn=update_auth_fields,
        inputs=[spec_choice],
        outputs=[identitynow_auth, okta_auth, iiq_auth]
    )
    
    refresh_eps.click(
        fn=update_acc,
        inputs=spec_choice,
        outputs=[*[accordion_placeholders[i][j] for i in range(max_groups) for j in range(2)], loading_status]
    )
    
    confirm_endpoints_btn.click(
        fn=confirm_selected_endpoints,
        inputs=[
            spec_choice,
            *[acc_cb[1] for acc_cb in accordion_placeholders]
        ],
        outputs=[
            confirmed_endpoints_state,
            display_values_state,
            param_group,
            param_header,  # Add param_header to outputs
            *[item for group, display, input_box in param_components 
            for item in (group, display, input_box)]
        ]
    )
    
    call_api_btn.click(
        fn=handle_api_call,
        inputs=[
            spec_choice,
            api_base_url,
            session_id_state,
            grant_type,
            client_id,
            client_secret,
            api_token,
            iiq_username,
            iiq_password,
            display_values_state,
            *[input_box for _, _, input_box in param_components],
            *[acc_cb[1] for acc_cb in accordion_placeholders]
        ],
        outputs=[responses_out, download_out, session_id_state, loading_status]
    )
    
if __name__ == "__main__":
    demo.launch(
        favicon_path="https://www.sailpoint.com/wp-content/uploads/2020/08/favicon.png",
        show_error=True
    )
import requests
import re
import sys

# Nginx Proxy Manager Configuration
npm_host = "http://localhost:81"  # URL of NPM
npm_user = "Change_user"            # NPM Admin
npm_password = "Change_password"     # NPM Admin Password

# Autenticación y obtención del token de acceso
def get_access_token():
    url = f"{npm_host}/api/tokens"
    payload = {
        "identity": npm_user,
        "secret": npm_password
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()["token"]

# Creación de un nuevo Proxy Host en NPM
def create_proxy_host(access_token, site_config):
    url = f"{npm_host}/api/nginx/proxy-hosts"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.post(url, headers=headers, json=site_config)
    response.raise_for_status()
    return response.json()

# Parsear un archivo de configuración Nginx
def parse_nginx_config(nginx_config):
    servers = []
    server_blocks = re.split(r'\n\s*server\s*\{', nginx_config)
    for block in server_blocks[1:]:
        server = {}
        server["server_name"] = re.search(r'server_name\s+([^\s;]+);', block).group(1)
        server["ssl_certificate"] = re.search(r'ssl_certificate\s+([^\s;]+);', block).group(1)
        server["ssl_certificate_key"] = re.search(r'ssl_certificate_key\s+([^\s;]+);', block).group(1)
        server["listen_port"] = int(re.search(r'listen\s+\S+:(\d+)\s+ssl;', block).group(1))

        locations = re.findall(r'location\s+([^\s\{]+)\s*\{[^\}]*proxy_pass\s+(\S+);', block)
        server["locations"] = [{"path": loc[0], "proxy_pass": loc[1]} for loc in locations]

        servers.append(server)
    return servers

# Convertir los datos parseados a la configuración del API de NPM
def convert_to_npm_config(server):
    forward_host_port = server["locations"][0]["proxy_pass"].replace("http://", "").replace("https://", "").split(":")
    forward_host = forward_host_port[0]
    forward_port = int(forward_host_port[1]) if len(forward_host_port) > 1 else (443 if server["listen_port"] == 443 else 80)

    # Crear configuración avanzada con custom locations
    advanced_config = ""
    for loc in server["locations"]:
        loc_forward_host_port = loc["proxy_pass"].replace("http://", "").replace("https://", "").split(":")
        loc_forward_host = loc_forward_host_port[0]
        loc_forward_port = int(loc_forward_host_port[1]) if len(loc_forward_host_port) > 1 else (443 if server["listen_port"] == 443 else 80)
        advanced_config += f"""
        location {loc["path"]} {{
            proxy_pass {loc["proxy_pass"]};
        }}
        """

    return {
        "domain_names": [server["server_name"]],
        "forward_scheme": "http" if forward_port == 80 else "https",
        "forward_host": forward_host,
        "forward_port": forward_port,
        "access_list_id": 0,
        "certificate_id": 0,  # Deberías configurar esto según tus necesidades de SSL
        "ssl_forced": True,
        "caching_enabled": False,
        "block_exploits": False,
        "advanced_config": advanced_config.strip(),
        "meta": {
            "letsencrypt_agree": False,
            "dns_challenge": False
        }
    }

# Función principal para manejar el archivo de configuración
def main(nginx_config_path):
    # Leer archivo de configuración Nginx
    with open(nginx_config_path, "r") as file:
        nginx_config = file.read()

    # Parsear y convertir configuraciones
    servers = parse_nginx_config(nginx_config)
    token = get_access_token()

    for server in servers:
        npm_config = convert_to_npm_config(server)
        response = create_proxy_host(token, npm_config)
        print(f"Sitio {server['server_name']} creado: {response}")

# Verificación de la línea de comando
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python script.py /ruta/al/archivo/de/configuracion/nginx.conf")
        sys.exit(1)

    nginx_config_path = sys.argv[1]
    main(nginx_config_path)

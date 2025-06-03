from dotenv import load_dotenv
from fastapi import FastAPI, status, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from openai import OpenAI
from io import BytesIO
import os
import secrets
import pandas as pd
import psycopg2
import openai # Importar explicitamente para openai.APIError
import datetime # Importe datetime para manipular datas e horas

# Carregar variáveis de ambiente
load_dotenv()

# Variáveis de conexão com PostgreSQL
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Função para conectar ao PostgreSQL
def get_db_connection():
    print("Tentando obter conexão com o banco de dados...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            # Adicionar esta linha para forçar o encoding na string de conexão
            options="-c client_encoding=UTF8"
        )
        # Manter esta linha também para garantir
        conn.set_client_encoding('UTF8')
        print("Conexão com o banco de dados estabelecida com sucesso.")
        return conn
    except Exception as e:
        print(f"Erro ao conectar ao banco de dados: {type(e).__name__}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Falha ao conectar ao banco de dados.")

class ChatInput(BaseModel):
    pergunta: str

# ====================================================================
# MOVIDO: Autenticação básica para acesso ao painel admin
# A definição de 'security' e 'autenticar' DEVE vir antes de
# qualquer rota que as use.
# ====================================================================
security = HTTPBasic()

def autenticar(credentials: HTTPBasicCredentials = Depends(security)):
    usuario_correto = secrets.compare_digest(credentials.username, "PEadmin")
    senha_correta = secrets.compare_digest(credentials.password, "@PernaB243567")
    if not (usuario_correto and senha_correta):
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Basic"}
        )
    return credentials.username
# ====================================================================

# Página inicial (chat)
@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open(os.path.join("static", "index.html"), "r", encoding="utf-8") as file:
        return file.read()

# Endpoint do chat
@app.post("/chat")
async def chat_pergunta(body: ChatInput):
    print(f"[{__name__}] Pergunta recebida (bruta): '{body.pergunta}'")
    print(f"[{__name__}] Tipo da pergunta: {type(body.pergunta)}")

    pergunta_lower = body.pergunta.lower().strip()
    print(f"[{__name__}] Pergunta formatada: '{pergunta_lower}'")

    # Detecção de intenção de simulação
    if "quero simular" in pergunta_lower or "simular" in pergunta_lower:
        print(f"[{__name__}] Intenção de simulação detectada.")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT nome, link_simulacao FROM motos')
            motos_data = cursor.fetchall()

            resposta = "Certo! Qual dessas motos você deseja simular?<br><br>"
            for nome, link in motos_data:
                resposta += f"""
                <div style="margin-bottom: 10px;">
                  <strong>{nome}</strong><br>
                  <a href="{link}" target="_blank" style="display: inline-block; padding: 6px 12px; background: #cc0000; color: white; text-decoration: none; border-radius: 4px;">Simular</a>
                </div>
                """
            print(f"[{__name__}] Resposta de simulação gerada. Tentando registrar no histórico...")
            # Registrar pergunta/resposta sem codificação explícita
            cursor.execute(
                "INSERT INTO historico_perguntas (pergunta, resposta) VALUES (%s, %s)",
                (body.pergunta, resposta) # Removido .encode('utf-8')
            )
            conn.commit()
            print(f"[{__name__}] Simulação e registro no histórico concluídos.")
        except Exception as e:
            conn.rollback() # Rollback em caso de erro
            print(f"[{__name__}] Erro ao processar simulação ou registrar histórico: {type(e).__name__}: {e}")
            return JSONResponse(content={"resposta": "Desculpe, houve um erro ao processar sua solicitação de simulação. Tente novamente mais tarde."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            conn.close()

        return JSONResponse(content={"resposta": resposta})

    # Chamada à OpenAI para perguntas gerais
    print(f"[{__name__}] Nenhuma intenção de simulação detectada. Chamando OpenAI...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": """
                    Você é um atendente especializado em consórcios da Pernambuco Motos (Pe Motos). Seu objetivo é fornecer respostas claras, objetivas e precisas, sem enrolação, sempre levando em consideração os regulamentos e as condições dos consórcios de aquisição de produtos da Honda, como motos e outros veículos.

                    Suas respostas devem ser baseadas nos seguintes pontos principais:
                    1. **Clareza nas condições**: Explique detalhadamente as condições do consórcio, como prazos, taxas de administração, contemplação, e valores de parcelas, sem usar jargões ou termos complicados.
                    2. **Compreensão das regras**: Certifique-se de que o cliente compreenda como o consórcio funciona, destacando aspectos como o sorteio, a carta de crédito, e os custos adicionais, como taxas de adesão e custos financeiros.
                    3. **Objetividade**: Respostas diretas, evitando informações desnecessárias ou evasivas. Lembre-se de que a transparência é essencial no atendimento.
                    4. **Flexibilidade**: Informe o cliente sobre as diferentes opções de planos de consórcio, prazos e valores que podem ser adaptados de acordo com o perfil do cliente, sempre alinhando a solução ao seu perfil financeiro.
                    5. **Atendimento ao cliente**: Sempre se mostre disponível para esclarecer dúvidas adicionais e nunca deixe de fazer o cliente se sentir confortável e bem atendido.

                    Se a questão não for clara o suficiente, pergunte de maneira cortês e objetiva para entender melhor o que o cliente deseja saber.
                """},
                {"role": "user", "content": body.pergunta}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        resposta = response.choices[0].message.content.strip()
        print(f"[{__name__}] Resposta da OpenAI recebida. Tentando registrar no histórico...")

        # Registrar pergunta/resposta sem codificação explícita
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO historico_perguntas (pergunta, resposta) VALUES (%s, %s)",
                (body.pergunta, resposta) # Removido .encode('utf-8')
            )
            conn.commit()
            print(f"[{__name__}] Registro no histórico da OpenAI concluído.")
        except Exception as e:
            conn.rollback()
            print(f"[{__name__}] Erro ao registrar histórico da OpenAI: {type(e).__name__}: {e}")
        finally:
            conn.close()

        return JSONResponse(content={"resposta": resposta})
    except openai.APIError as e:
        print(f"[{__name__}] Erro da API OpenAI: {type(e).__name__}: {e}")
        return JSONResponse(content={"resposta": "Desculpe, a OpenAI está com problemas no momento. Tente novamente mais tarde."}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as e:
        print(f"[{__name__}] Erro inesperado no chat: {type(e).__name__}: {e}")
        return JSONResponse(content={"resposta": "Desculpe, houve um erro ao tentar responder. Tente novamente mais tarde."}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Registrar acesso ao chat
@app.post("/registrar-acesso", status_code=status.HTTP_204_NO_CONTENT)
async def registrar_acesso():
    print(f"[{__name__}] Tentando registrar acesso...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        print(f"[{__name__}] Conexão e cursor para registro de acesso obtidos.")
        cursor.execute("INSERT INTO acessos_chat DEFAULT VALUES")
        conn.commit()
        print(f"[{__name__}] Acesso registrado com sucesso.")
        conn.close()
    except Exception as e:
        print(f"[{__name__}] Erro detalhado ao registrar acesso: {type(e).__name__}: {e}")
        # Retornamos 204 No Content, então não podemos retornar um JSONResponse com erro diretamente.
        # A mensagem de erro será apenas no log do servidor.

# Retornar motos para simulação
@app.get("/motos")
async def get_motos():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT nome, link_simulacao FROM motos')
        motos_data = cursor.fetchall()
        motos = [{"nome": nome, "link_simulacao": link} for nome, link in motos_data]
        return JSONResponse(content=motos)
    except Exception as e:
        print(f"[{__name__}] Erro ao buscar motos: {type(e).__name__}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao buscar dados das motos.")
    finally:
        conn.close()

# Ver total de acessos
@app.get("/admin/acessos")
async def contar_acessos(user: str = Depends(autenticar)): # APLIQUEI AUTENTICAÇÃO AQUI
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM acessos_chat")
        total = cursor.fetchone()[0]
        return {"total_acessos": total}
    except Exception as e:
        print(f"[{__name__}] Erro ao contar acessos: {type(e).__name__}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao contar acessos.")
    finally:
        conn.close()

# Ver histórico de perguntas
@app.get("/admin/perguntas")
async def listar_perguntas(user: str = Depends(autenticar)): # APLIQUEI AUTENTICAÇÃO AQUI
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT pergunta, resposta, timestamp FROM historico_perguntas ORDER BY timestamp DESC")
        historico = cursor.fetchall()

        # Prepara os dados para o JSON, decodificando se for necessário
        formatted_historico = []
        for p, r, t in historico:
            # Tenta decodificar se for uma string de bytes, senão mantém como está
            # Adicionado errors='ignore' para evitar quebrar em caso de bytes inválidos
            pergunta_str = p.decode('utf-8', errors='ignore') if isinstance(p, bytes) else p
            resposta_str = r.decode('utf-8', errors='ignore') if isinstance(r, bytes) else r
            formatted_historico.append({
                "pergunta": pergunta_str,
                "resposta": resposta_str,
                "timestamp": t.isoformat() if t else None # Converte datetime para string no formato ISO
            })
        return JSONResponse(content=formatted_historico)
    except Exception as e:
        print(f"[{__name__}] Erro ao listar perguntas: {type(e).__name__}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao listar perguntas.")
    finally:
        conn.close()

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(user: str = Depends(autenticar)):
    with open(os.path.join("static", "admin.html"), "r", encoding="utf-8") as f:
        return f.read()

# Endpoint para exportar acessos para Excel
@app.get("/admin/exportar-acessos")
async def exportar_acessos(user: str = Depends(autenticar)): # APLIQUEI AUTENTICAÇÃO AQUI
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, timestamp FROM acessos_chat ORDER BY timestamp DESC")
        acessos = cursor.fetchall()

        # Criar um DataFrame com os dados
        # Converter timestamps para timezone-unaware
        df_acessos = pd.DataFrame(acessos, columns=["ID", "Timestamp"])
        df_acessos["Timestamp"] = df_acessos["Timestamp"].apply(
            lambda x: x.replace(tzinfo=None) if isinstance(x, datetime.datetime) and x.tzinfo is not None else x
        )

        # Gerar o arquivo Excel em memória
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_acessos.to_excel(writer, index=False, sheet_name="Acessos")

        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=acessos.xlsx"})
    except Exception as e:
        print(f"[{__name__}] Erro ao exportar acessos: {type(e).__name__}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao exportar dados de acessos.")
    finally:
        conn.close()

# Endpoint para exportar histórico de perguntas para Excel
@app.get("/admin/exportar-perguntas")
async def exportar_perguntas(user: str = Depends(autenticar)): # APLIQUEI AUTENTICAÇÃO AQUI
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT pergunta, resposta, timestamp FROM historico_perguntas ORDER BY timestamp DESC")
        historico = cursor.fetchall()

        # Prepara os dados para o DataFrame, decodificando se necessário
        processed_data = []
        for p, r, t in historico:
            pergunta_str = p.decode('utf-8', errors='ignore') if isinstance(p, bytes) else p
            resposta_str = r.decode('utf-8', errors='ignore') if isinstance(r, bytes) else r
            # Converter timestamp para timezone-unaware se for datetime com fuso horário
            timestamp_unaware = t.replace(tzinfo=None) if isinstance(t, datetime.datetime) and t.tzinfo is not None else t
            processed_data.append([pergunta_str, resposta_str, timestamp_unaware])

        # Criar um DataFrame com os dados
        df_perguntas = pd.DataFrame(processed_data, columns=["Pergunta", "Resposta", "Timestamp"])

        # Gerar o arquivo Excel em memória
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_perguntas.to_excel(writer, index=False, sheet_name="Perguntas")

        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=historico_perguntas.xlsx"})
    except Exception as e:
        print(f"[{__name__}] Erro ao exportar perguntas: {type(e).__name__}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao exportar dados de perguntas.")
    finally:
        conn.close()
🤖 Bot DCAN - Processador de Tickets e Notas Fiscais via WhatsApp\
Este projeto é um bot de WhatsApp construído com Flask, integrado com APIs externas como Google Vision, Supabase, A3Soft(TMS) e Z-API.\
Ele processa imagens de tickets e notas fiscais enviadas por motoristas e automatiza o registro dos dados.

📁 Estrutura do Projeto\
bot_dcan/\
├── main.py                       # Arquivo principal com webhook Flask\
├── config.py                     # Configurações gerais do bot\
├── mensagens.py                  # Envio de mensagens e botões via Z-API\
├── integracoes/                  # Integrações externas\
│   ├── azure.py\
│   ├── google_sheets.py\
│   ├── google_vision.py\
│   └── supabase.py\
├── a3soft                       # Sistema TMS utilizado\   
│   ├── client.py\
│   └── routes.py\
├── operacao/                    # Opção Operação na lista de Areas\
│   ├── falar_programador/       # Contato dos programadores\  
│   │   └── contato.py\
│   ├── foto_nf/                 # Tratamento .pdf ou .png das NF's\
│   │   ├── defs.py\
│   │   └── estados.py\
│   ├── foto_ticket/             # Arquivo individual para cada Cliente com Ticket\
│   │   ├── arcelormittal.py\
│   │   ├── cdr.py\
│   │   ├── defs.py\
│   │   ├── estados.py\
│   │   ├── gerdau.py\
│   │   ├── gerdaupinda.py\
│   │   ├── mahle.py\
│   │   ├── orizon.py\
│   │   ├── rio_das_pedras.py\
│   │   └── saae.py\
\
💡 Funcionalidades
- Processamento de imagem com OCR (Google Vision)
- Extração dos dados de tickets por cliente
- Extração da chave de acesso NF-e
- Consulta NF-e via NSDocs
- Envio de dados para SupaBase
- Upload de imagem para AzureFiles
- Informações extraídas enviadas para Supabase
- Uso de botões e listas via Z-API

✨ Créditos\
Projeto interno DCAN Transportes — desenvolvido para automatizar e agilizar o processo logístico de recebimento de documentos.\
Desenvolvido por Gustavo Natan de Oliveira.

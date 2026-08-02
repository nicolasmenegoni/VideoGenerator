#!/bin/bash
# Script para rodar o app no navegador com backend Flask

echo "Iniciando servidor backend..."
python3 server.py &
SERVER_PID=$!

# Aguarda o servidor iniciar
sleep 2

# Abre no navegador
echo "Abrindo no navegador..."
xdg-open http://localhost:5001 || open http://localhost:5001 || echo "Abra manualmente: http://localhost:5001"

# Mantém o script rodando
wait $SERVER_PID

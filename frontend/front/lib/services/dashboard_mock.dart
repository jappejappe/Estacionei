// Dados fictícios que alimentam o painel de vagas (mock até integrar API/banco).

const int totalVagas = 120;
const int vagasOcupadas = 89;
const int vagasDisponiveis = totalVagas - vagasOcupadas;
const double taxaOcupacao = (vagasOcupadas / totalVagas) * 100;

/// Histórico fictício de ocupação ao longo do dia para o gráfico de linha.
const List<Map<String, dynamic>> historicoHorarios = [
  {'hora': '08:00', 'ocupadas': 30},
  {'hora': '10:00', 'ocupadas': 65},
  {'hora': '12:00', 'ocupadas': 95},
  {'hora': '14:00', 'ocupadas': 89},
  {'hora': '16:00', 'ocupadas': 102},
  {'hora': '18:00', 'ocupadas': 78},
];

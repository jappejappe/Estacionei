import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:front/services/dashboard_mock.dart';

/// Painel de vagas com indicadores, gráficos e alertas inteligentes (dados mock).
class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key});

  static const double _cardRadius = 12;
  static const EdgeInsets _pagePadding = EdgeInsets.all(16);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Painel de Vagas'),
        backgroundColor: const Color(0xFF000000),
        foregroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: _pagePadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildCards(),
            const SizedBox(height: 16),
            _buildPieChart(),
            const SizedBox(height: 16),
            _buildLineChart(),
            const SizedBox(height: 16),
            _buildAlerta(),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  /// Renderiza os 3 cards de resumo: disponíveis, ocupadas e taxa de ocupação.
  Widget _buildCards() {
    return Row(
      children: [
        Expanded(
          child: _buildResumoCard(
            icon: Icons.check_circle,
            cor: Colors.green,
            valor: '$vagasDisponiveis',
            rotulo: 'Disponíveis',
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _buildResumoCard(
            icon: Icons.cancel,
            cor: Colors.red,
            valor: '$vagasOcupadas',
            rotulo: 'Ocupadas',
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _buildResumoCard(
            icon: Icons.pie_chart,
            cor: Colors.orange,
            valor: '${taxaOcupacao.toStringAsFixed(1)}%',
            rotulo: 'Ocupação',
          ),
        ),
      ],
    );
  }

  Widget _buildResumoCard({
    required IconData icon,
    required Color cor,
    required String valor,
    required String rotulo,
  }) {
    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(_cardRadius),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
        child: Column(
          children: [
            Icon(icon, color: cor, size: 28),
            const SizedBox(height: 8),
            Text(
              valor,
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 4),
            Text(
              rotulo,
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey[600],
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  /// Renderiza o gráfico de pizza com a distribuição atual de vagas livres e ocupadas.
  Widget _buildPieChart() {
    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(_cardRadius),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Distribuição Atual',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 200,
              child: PieChart(
                PieChartData(
                  sectionsSpace: 2,
                  centerSpaceRadius: 40,
                  sections: [
                    PieChartSectionData(
                      value: vagasDisponiveis.toDouble(),
                      color: Colors.green,
                      title: 'Livres',
                      radius: 50,
                      titleStyle: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                    PieChartSectionData(
                      value: vagasOcupadas.toDouble(),
                      color: Colors.red,
                      title: 'Ocupadas',
                      radius: 50,
                      titleStyle: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            _buildLegendaItem(Colors.green, 'Livres ($vagasDisponiveis)'),
            const SizedBox(height: 6),
            _buildLegendaItem(Colors.red, 'Ocupadas ($vagasOcupadas)'),
          ],
        ),
      ),
    );
  }

  Widget _buildLegendaItem(Color cor, String texto) {
    return Row(
      children: [
        Container(
          width: 14,
          height: 14,
          decoration: BoxDecoration(
            color: cor,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
        const SizedBox(width: 8),
        Text(texto),
      ],
    );
  }

  /// Renderiza o gráfico de linha com o histórico de horários de pico do dia.
  Widget _buildLineChart() {
    final pontos = List<FlSpot>.generate(
      historicoHorarios.length,
      (index) => FlSpot(
        index.toDouble(),
        (historicoHorarios[index]['ocupadas'] as int).toDouble(),
      ),
    );

    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(_cardRadius),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Horários de Pico',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 220,
              child: LineChart(
                LineChartData(
                  minX: 0,
                  maxX: (historicoHorarios.length - 1).toDouble(),
                  minY: 0,
                  maxY: 120,
                  gridData: FlGridData(
                    show: true,
                    drawVerticalLine: false,
                    horizontalInterval: 30,
                    getDrawingHorizontalLine: (value) => FlLine(
                      color: Colors.grey.shade300,
                      strokeWidth: 1,
                    ),
                  ),
                  borderData: FlBorderData(
                    show: true,
                    border: Border(
                      bottom: BorderSide(color: Colors.grey.shade400),
                      left: BorderSide(color: Colors.grey.shade400),
                    ),
                  ),
                  titlesData: FlTitlesData(
                    topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false),
                    ),
                    rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false),
                    ),
                    leftTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 32,
                        interval: 30,
                        getTitlesWidget: (value, meta) => Text(
                          value.toInt().toString(),
                          style: const TextStyle(fontSize: 10),
                        ),
                      ),
                    ),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 28,
                        getTitlesWidget: (value, meta) {
                          final index = value.toInt();
                          if (index < 0 || index >= historicoHorarios.length) {
                            return const SizedBox.shrink();
                          }
                          return Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(
                              historicoHorarios[index]['hora'] as String,
                              style: const TextStyle(fontSize: 10),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                  lineBarsData: [
                    LineChartBarData(
                      spots: pontos,
                      isCurved: true,
                      color: Colors.blue,
                      barWidth: 3,
                      dotData: const FlDotData(show: true),
                      belowBarData: BarAreaData(
                        show: true,
                        color: Colors.blue.withValues(alpha: 0.2),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Renderiza o bloco de alerta inteligente conforme a taxa de ocupação atual.
  Widget _buildAlerta() {
    late Color fundo;
    late Color borda;
    late Color corIcone;
    late IconData icone;
    late String mensagem;

    if (taxaOcupacao >= 85) {
      fundo = Colors.amber.shade100;
      borda = Colors.amber.shade700;
      corIcone = Colors.amber.shade800;
      icone = Icons.warning_amber_rounded;
      mensagem =
          'O centro está muito movimentado agora. Considere planejar seu destino com antecedência.';
    } else if (taxaOcupacao < 50) {
      fundo = Colors.green.shade100;
      borda = Colors.green.shade700;
      corIcone = Colors.green.shade700;
      icone = Icons.check_circle_outline;
      mensagem =
          'Estacionamento tranquilo! Muitas vagas disponíveis nas proximidades.';
    } else {
      fundo = Colors.blue.shade100;
      borda = Colors.blue.shade700;
      corIcone = Colors.blue.shade700;
      icone = Icons.info_outline;
      mensagem =
          'Movimento moderado. Algumas vagas disponíveis na região central.';
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: fundo,
        borderRadius: BorderRadius.circular(_cardRadius),
        border: Border(
          left: BorderSide(color: borda, width: 4),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icone, color: corIcone, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              mensagem,
              style: const TextStyle(fontSize: 14, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}

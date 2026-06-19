import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

// ---------------------------------------------------------------------------
// Configuração da API
// ---------------------------------------------------------------------------

/// Retorna a base URL correta dependendo da plataforma.
/// No emulador Android, `localhost` aponta para o host via 10.0.2.2.
String get apiBaseUrl {
  if (kIsWeb) return 'http://localhost:1421';
  if (Platform.isAndroid) return 'http://10.0.2.2:1421';
  return 'http://localhost:1421';
}

// ---------------------------------------------------------------------------
// Modelo de dados
// ---------------------------------------------------------------------------

/// Representa uma vaga de estacionamento retornada pela API.
class VagaEstacionamento {
  final int id;
  final String codigoVaga;
  final double latitude;
  final double longitude;
  final int status; // 0 = Livre, 1 = Ocupada
  final String ultimaAtualizacao;

  const VagaEstacionamento({
    required this.id,
    required this.codigoVaga,
    required this.latitude,
    required this.longitude,
    required this.status,
    required this.ultimaAtualizacao,
  });

  /// Constrói a partir do JSON da API.
  /// Trata latitude/longitude como String ou num, lidando com a notação "0E-8".
  factory VagaEstacionamento.fromJson(Map<String, dynamic> json) {
    return VagaEstacionamento(
      id: json['id'] as int,
      codigoVaga: (json['codigo_vaga'] ?? '').toString(),
      latitude: _parseCoord(json['latitude']),
      longitude: _parseCoord(json['longitude']),
      status: (json['status'] as int?) ?? 0,
      ultimaAtualizacao: (json['ultima_atualizacao'] ?? '').toString(),
    );
  }

  /// Verifica se a coordenada é válida (diferente de zero / nulo).
  bool get temCoordenadaValida =>
      latitude.abs() > 0.0001 && longitude.abs() > 0.0001;

  /// Converte dinamicamente o campo de coordenada para double.
  static double _parseCoord(dynamic value) {
    if (value == null) return 0.0;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString()) ?? 0.0;
  }
}

// ---------------------------------------------------------------------------
// Tela do Mapa
// ---------------------------------------------------------------------------

/// Tela principal do Estacionei — mapa de Concórdia - SC com busca e centralização.
class MapaPage extends StatefulWidget {
  const MapaPage({super.key});

  @override
  State<MapaPage> createState() => _MapaPageState();
}

class _MapaPageState extends State<MapaPage> with TickerProviderStateMixin {
  // Coordenadas fixas de Concórdia - SC (dados mock até integrar API/banco)
  static const double _latitude = -27.2342;
  static const double _longitude = -52.0270;
  static const double _zoomInicial = 14.0;

  /// Controla a câmera do mapa (zoom, pan e recentralização programática).
  final MapController _mapController = MapController();

  LatLng get _centroConcordia => const LatLng(_latitude, _longitude);

  /// Lista de vagas carregadas da API.
  List<VagaEstacionamento> _vagas = [];

  /// Indica se está fazendo a primeira carga (exibe indicador de progresso).
  bool _carregando = true;

  /// Mensagem de erro (se houver) para exibir ao usuário.
  String? _erro;

  /// Timer para atualização periódica das vagas.
  Timer? _timerAtualizacao;

  // -----------------------------------------------------------------------
  // Ciclo de vida
  // -----------------------------------------------------------------------

  @override
  void initState() {
    super.initState();
    _carregarVagas();
    // Atualiza os status a cada 10 segundos.
    _timerAtualizacao = Timer.periodic(
      const Duration(seconds: 10),
      (_) => _carregarVagas(),
    );
  }

  @override
  void dispose() {
    _timerAtualizacao?.cancel();
    super.dispose();
  }

  // -----------------------------------------------------------------------
  // Fetch da API
  // -----------------------------------------------------------------------

  /// Busca as vagas no endpoint `/api/statusVagas/`.
  Future<void> _carregarVagas() async {
    try {
      final url = Uri.parse('$apiBaseUrl/api/statusVagas/');
      final response = await http.get(url).timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final List<dynamic> jsonList = json.decode(response.body);
        setState(() {
          _vagas = jsonList
              .map((j) => VagaEstacionamento.fromJson(j as Map<String, dynamic>))
              .toList();
          _carregando = false;
          _erro = null;
        });
      } else {
        setState(() {
          _erro = 'Erro ${response.statusCode}';
          _carregando = false;
        });
      }
    } catch (e) {
      setState(() {
        _erro = 'Sem conexão com a API';
        _carregando = false;
      });
    }
  }

  // -----------------------------------------------------------------------
  // Posicionamento de Fallback
  // -----------------------------------------------------------------------

  /// Para vagas sem coordenadas válidas, distribui em grade ao redor do centro.
  LatLng _posicaoFallback(int indice) {
    // Gera uma grade 5 colunas ao redor do centro de Concórdia.
    const int colunas = 5;
    final int linha = indice ~/ colunas;
    final int coluna = indice % colunas;

    // Offset em graus (~11m por 0.0001°).
    const double espacamento = 0.0008;
    final double lat = _latitude + 0.002 - (linha * espacamento);
    final double lng = _longitude - 0.002 + (coluna * espacamento);
    return LatLng(lat, lng);
  }

  // -----------------------------------------------------------------------
  // Ações
  // -----------------------------------------------------------------------

  /// Recentraliza o mapa nas coordenadas iniciais de Concórdia.
  void _centralizarMapa() {
    _mapController.move(_centroConcordia, _zoomInicial);
  }

  /// Exibe um BottomSheet com detalhes da vaga selecionada.
  void _mostrarDetalhesVaga(VagaEstacionamento vaga) {
    final bool livre = vaga.status == 0;

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        return Container(
          decoration: const BoxDecoration(
            color: Color(0xFF1E1E2C),
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Indicador de arraste
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),

              // Linha com código e status
              Row(
                children: [
                  // Ícone de status
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: livre
                          ? const Color(0xFF00C853).withValues(alpha: 0.15)
                          : const Color(0xFFFF1744).withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(
                      livre ? Icons.check_circle_rounded : Icons.block_rounded,
                      color: livre
                          ? const Color(0xFF00C853)
                          : const Color(0xFFFF1744),
                      size: 28,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Vaga ${vaga.codigoVaga}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 3),
                          decoration: BoxDecoration(
                            color: livre
                                ? const Color(0xFF00C853).withValues(alpha: 0.2)
                                : const Color(0xFFFF1744).withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            livre ? 'Disponível' : 'Ocupada',
                            style: TextStyle(
                              color: livre
                                  ? const Color(0xFF00C853)
                                  : const Color(0xFFFF1744),
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 20),
              const Divider(color: Colors.white12),
              const SizedBox(height: 12),

              // Detalhes
              _detalheRow(Icons.tag_rounded, 'ID', '${vaga.id}'),
              const SizedBox(height: 10),
              _detalheRow(
                Icons.access_time_rounded,
                'Última Atualização',
                _formatarData(vaga.ultimaAtualizacao),
              ),
              const SizedBox(height: 10),
              _detalheRow(
                Icons.location_on_rounded,
                'Coordenadas',
                vaga.temCoordenadaValida
                    ? '${vaga.latitude.toStringAsFixed(6)}, ${vaga.longitude.toStringAsFixed(6)}'
                    : 'Posição de teste',
              ),
              const SizedBox(height: 20),
            ],
          ),
        );
      },
    );
  }

  /// Linha de detalhe reutilizável para o BottomSheet.
  Widget _detalheRow(IconData icon, String label, String valor) {
    return Row(
      children: [
        Icon(icon, color: Colors.white38, size: 18),
        const SizedBox(width: 10),
        Text(
          '$label: ',
          style: const TextStyle(
            color: Colors.white54,
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
        Expanded(
          child: Text(
            valor,
            style: const TextStyle(color: Colors.white, fontSize: 13),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }

  /// Formata a string de data vinda da API para algo mais legível.
  String _formatarData(String raw) {
    if (raw.isEmpty) return '—';
    try {
      final dt = DateTime.parse(raw);
      return '${dt.day.toString().padLeft(2, '0')}/'
          '${dt.month.toString().padLeft(2, '0')}/'
          '${dt.year} '
          '${dt.hour.toString().padLeft(2, '0')}:'
          '${dt.minute.toString().padLeft(2, '0')}';
    } catch (_) {
      // A API retorna no formato "Fri, 29 May 2026 08:38:50 GMT" — tenta HttpDate.
      try {
        final dt = _parseHttpDate(raw);
        if (dt != null) {
          return '${dt.day.toString().padLeft(2, '0')}/'
              '${dt.month.toString().padLeft(2, '0')}/'
              '${dt.year} '
              '${dt.hour.toString().padLeft(2, '0')}:'
              '${dt.minute.toString().padLeft(2, '0')}';
        }
      } catch (_) {}
      return raw;
    }
  }

  /// Tenta parsear datas no formato HTTP (ex: "Fri, 29 May 2026 08:38:50 GMT").
  DateTime? _parseHttpDate(String raw) {
    const meses = {
      'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
      'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
    };
    // "Fri, 29 May 2026 08:38:50 GMT"
    final parts = raw.replaceAll(',', '').split(' ');
    if (parts.length < 5) return null;
    final dia = int.tryParse(parts[1]);
    final mes = meses[parts[2]];
    final ano = int.tryParse(parts[3]);
    final timeParts = parts[4].split(':');
    if (dia == null || mes == null || ano == null || timeParts.length < 3) {
      return null;
    }
    return DateTime(
      ano, mes, dia,
      int.tryParse(timeParts[0]) ?? 0,
      int.tryParse(timeParts[1]) ?? 0,
      int.tryParse(timeParts[2]) ?? 0,
    );
  }

  // -----------------------------------------------------------------------
  // Build
  // -----------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // Mapa em tela cheia; overlays ficam no Stack (sem AppBar).
      body: Stack(
        children: [
          _buildMapa(),
          _buildBarraDePesquisa(),
          _buildIndicadorStatus(),
          _buildBotaoDashboard(),
          _buildBotaoAtualizar(),
          _buildBotaoCentralizar(),
        ],
      ),
    );
  }

  /// Camada base: FlutterMap com tiles OpenStreetMap ocupando 100% da tela.
  Widget _buildMapa() {
    return Positioned.fill(
      child: FlutterMap(
        mapController: _mapController,
        options: MapOptions(
          initialCenter: _centroConcordia,
          initialZoom: _zoomInicial,
        ),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.example.front',
          ),
          // Camada de marcadores das vagas
          MarkerLayer(markers: _buildMarcadoresVagas()),
        ],
      ),
    );
  }

  /// Gera a lista de Markers para cada vaga.
  List<Marker> _buildMarcadoresVagas() {
    return List.generate(_vagas.length, (i) {
      final vaga = _vagas[i];
      final LatLng posicao = vaga.temCoordenadaValida
          ? LatLng(vaga.latitude, vaga.longitude)
          : _posicaoFallback(i);

      final bool livre = vaga.status == 0;
      final Color corFundo = livre
          ? const Color(0xFF00C853) // verde vibrante
          : const Color(0xFFFF1744); // vermelho vibrante
      final Color corBorda = livre
          ? const Color(0xFF00E676)
          : const Color(0xFFFF5252);

      return Marker(
        point: posicao,
        width: 42,
        height: 42,
        child: GestureDetector(
          onTap: () => _mostrarDetalhesVaga(vaga),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 400),
            curve: Curves.easeInOut,
            decoration: BoxDecoration(
              color: corFundo.withValues(alpha: 0.85),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: corBorda, width: 2),
              boxShadow: [
                BoxShadow(
                  color: corFundo.withValues(alpha: 0.4),
                  blurRadius: 8,
                  spreadRadius: 1,
                ),
              ],
            ),
            alignment: Alignment.center,
            child: Text(
              vaga.codigoVaga,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.3,
              ),
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
    });
  }

  /// Barra de pesquisa flutuante no topo, abaixo da status bar.
  Widget _buildBarraDePesquisa() {
    final topoSeguro = MediaQuery.of(context).padding.top;

    return Positioned(
      top: topoSeguro + 8,
      left: 16,
      right: 16,
      child: Material(
        elevation: 4,
        borderRadius: BorderRadius.circular(12),
        color: Colors.white,
        child: TextField(
          decoration: InputDecoration(
            hintText: 'Buscar vagas de estacionamento...',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: IconButton(
              icon: const Icon(Icons.mic),
              onPressed: () {
                // Placeholder: reconhecimento de voz virá em versão futura.
              },
            ),
            filled: true,
            fillColor: Colors.white,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide.none,
            ),
            contentPadding: const EdgeInsets.symmetric(vertical: 14),
          ),
        ),
      ),
    );
  }

  /// Indicador de status: mostra um chip flutuante com contagem de vagas.
  Widget _buildIndicadorStatus() {
    final topoSeguro = MediaQuery.of(context).padding.top;

    if (_carregando && _vagas.isEmpty) {
      return Positioned(
        top: topoSeguro + 72,
        left: 16,
        right: 16,
        child: Center(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFF1E1E2C).withValues(alpha: 0.9),
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white70,
                  ),
                ),
                SizedBox(width: 10),
                Text(
                  'Carregando vagas...',
                  style: TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (_erro != null && _vagas.isEmpty) {
      return Positioned(
        top: topoSeguro + 72,
        left: 16,
        right: 16,
        child: Center(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFFFF1744).withValues(alpha: 0.85),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.wifi_off_rounded, color: Colors.white, size: 16),
                const SizedBox(width: 8),
                Text(
                  _erro!,
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (_vagas.isEmpty) return const SizedBox.shrink();

    final int livres = _vagas.where((v) => v.status == 0).length;
    final int ocupadas = _vagas.length - livres;

    return Positioned(
      top: topoSeguro + 72,
      left: 16,
      right: 16,
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: const Color(0xFF1E1E2C).withValues(alpha: 0.92),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.3),
                blurRadius: 8,
              ),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Livres
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  color: const Color(0xFF00C853),
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
              const SizedBox(width: 6),
              Text(
                '$livres livres',
                style: const TextStyle(
                  color: Color(0xFF00E676),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(width: 14),
              // Ocupadas
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  color: const Color(0xFFFF1744),
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
              const SizedBox(width: 6),
              Text(
                '$ocupadas ocupadas',
                style: const TextStyle(
                  color: Color(0xFFFF5252),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Botão flutuante no canto inferior esquerdo para abrir o painel de vagas.
  Widget _buildBotaoDashboard() {
    return Positioned(
      left: 16,
      bottom: 24,
      child: FloatingActionButton(
        heroTag: 'dashboard',
        onPressed: () => Navigator.pushNamed(context, '/dashboard'),
        tooltip: 'Painel de Vagas',
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF000000),
        child: const Icon(Icons.dashboard),
      ),
    );
  }

  /// Botão de atualização manual (refresh) acima do botão de centralizar.
  Widget _buildBotaoAtualizar() {
    return Positioned(
      right: 16,
      bottom: 90,
      child: FloatingActionButton.small(
        heroTag: 'atualizar',
        onPressed: _carregarVagas,
        tooltip: 'Atualizar vagas',
        backgroundColor: const Color(0xFF1E1E2C),
        foregroundColor: Colors.white,
        child: const Icon(Icons.refresh_rounded, size: 22),
      ),
    );
  }

  /// FAB no canto inferior direito para voltar ao centro de Concórdia.
  Widget _buildBotaoCentralizar() {
    return Positioned(
      right: 16,
      bottom: 24,
      child: FloatingActionButton(
        heroTag: 'centralizar',
        onPressed: _centralizarMapa,
        tooltip: 'Centralizar em Concórdia',
        child: const Icon(Icons.my_location),
      ),
    );
  }
}

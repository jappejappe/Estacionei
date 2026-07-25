import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;
import 'dart:math' as math;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart' hide Path;

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

  /// Distância em km até o ponto de destino (preenchida pelo filtro de proximidade).
  final double? distanciaKm;

  const VagaEstacionamento({
    required this.id,
    required this.codigoVaga,
    required this.latitude,
    required this.longitude,
    required this.status,
    required this.ultimaAtualizacao,
    this.distanciaKm,
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
      distanciaKm: json['distancia_km'] != null
          ? (json['distancia_km'] as num).toDouble()
          : null,
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

/// Representa um resultado de busca de endereço (geocoding).
class ResultadoBusca {
  final String nomeExibicao;
  final double latitude;
  final double longitude;

  const ResultadoBusca({
    required this.nomeExibicao,
    required this.latitude,
    required this.longitude,
  });

  factory ResultadoBusca.fromNominatimJson(Map<String, dynamic> json) {
    return ResultadoBusca(
      nomeExibicao: json['display_name'] as String,
      latitude: double.parse(json['lat'] as String),
      longitude: double.parse(json['lon'] as String),
    );
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
  // Estado do filtro de proximidade
  // -----------------------------------------------------------------------

  /// Ponto de destino selecionado pelo usuário.
  LatLng? _pontoDestino;

  /// Nome do endereço de destino (para exibir no chip).
  String? _nomeDestino;

  /// Raio do filtro de proximidade em km.
  double _raioFiltroKm = 0.5;

  /// Se o filtro de proximidade está ativo.
  bool _filtroProximidadeAtivo = false;

  /// Vagas filtradas por proximidade (retornadas pela API com distância).
  List<VagaEstacionamento>? _vagasProximas;

  /// Se está buscando vagas próximas.
  bool _buscandoProximas = false;

  // -----------------------------------------------------------------------
  // Estado da barra de busca
  // -----------------------------------------------------------------------

  final TextEditingController _buscaController = TextEditingController();
  final FocusNode _buscaFocusNode = FocusNode();

  /// Resultados da busca de endereço.
  List<ResultadoBusca> _resultadosBusca = [];

  /// Se está realizando geocoding.
  bool _buscandoEndereco = false;

  /// Timer de debounce para a busca.
  Timer? _debounce;

  /// Se o painel de resultados deve ser exibido.
  bool _mostrandoResultados = false;

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
      (_) => _filtroProximidadeAtivo ? _buscarVagasProximas() : _carregarVagas(),
    );

    _buscaFocusNode.addListener(() {
      if (!_buscaFocusNode.hasFocus) {
        // Pequeno delay para permitir clique nos resultados
        Future.delayed(const Duration(milliseconds: 200), () {
          if (mounted && !_buscaFocusNode.hasFocus) {
            setState(() => _mostrandoResultados = false);
          }
        });
      }
    });
  }

  @override
  void dispose() {
    _timerAtualizacao?.cancel();
    _debounce?.cancel();
    _buscaController.dispose();
    _buscaFocusNode.dispose();
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

  /// Busca vagas próximas ao ponto de destino via `/api/vagas/proximas`.
  Future<void> _buscarVagasProximas() async {
    if (_pontoDestino == null) return;

    setState(() => _buscandoProximas = true);

    try {
      final url = Uri.parse(
        '$apiBaseUrl/api/vagas/proximas'
        '?lat=${_pontoDestino!.latitude}'
        '&lon=${_pontoDestino!.longitude}'
        '&raio=$_raioFiltroKm',
      );
      final response = await http.get(url).timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final List<dynamic> jsonList = json.decode(response.body);
        setState(() {
          _vagasProximas = jsonList
              .map((j) => VagaEstacionamento.fromJson(j as Map<String, dynamic>))
              .toList();
          _buscandoProximas = false;
          _erro = null;
        });
      } else {
        setState(() {
          _buscandoProximas = false;
          _erro = 'Erro ao buscar vagas próximas';
        });
      }
    } catch (e) {
      setState(() {
        _buscandoProximas = false;
        _erro = 'Sem conexão com a API';
      });
    }
  }

  // -----------------------------------------------------------------------
  // Geocoding via Nominatim (OpenStreetMap)
  // -----------------------------------------------------------------------

  /// Busca endereços no Nominatim com base no texto digitado.
  Future<void> _buscarEndereco(String query) async {
    if (query.trim().length < 3) {
      setState(() {
        _resultadosBusca = [];
        _mostrandoResultados = false;
      });
      return;
    }

    setState(() => _buscandoEndereco = true);

    try {
      // Prioriza resultados em Concórdia-SC com viewbox
      final url = Uri.parse(
        'https://nominatim.openstreetmap.org/search'
        '?q=${Uri.encodeComponent(query)}'
        '&format=json'
        '&addressdetails=1'
        '&limit=5'
        '&viewbox=-52.10,-27.18,-51.95,-27.30'
        '&bounded=0'
        '&countrycodes=br',
      );

      final response = await http.get(
        url,
        headers: {'User-Agent': 'Estacionei-App/1.0'},
      ).timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final List<dynamic> jsonList = json.decode(response.body);
        setState(() {
          _resultadosBusca = jsonList
              .map((j) =>
                  ResultadoBusca.fromNominatimJson(j as Map<String, dynamic>))
              .toList();
          _buscandoEndereco = false;
          _mostrandoResultados = _resultadosBusca.isNotEmpty;
        });
      } else {
        setState(() => _buscandoEndereco = false);
      }
    } catch (e) {
      setState(() => _buscandoEndereco = false);
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

  /// Seleciona um destino a partir dos resultados de busca.
  void _selecionarDestino(ResultadoBusca resultado) {
    final destino = LatLng(resultado.latitude, resultado.longitude);

    setState(() {
      _pontoDestino = destino;
      _nomeDestino = _encurtarNome(resultado.nomeExibicao);
      _filtroProximidadeAtivo = true;
      _mostrandoResultados = false;
      _buscaController.text = _nomeDestino!;
    });

    _buscaFocusNode.unfocus();

    // Move o mapa para o destino
    _mapController.move(destino, 16.0);

    // Busca vagas próximas
    _buscarVagasProximas();
  }

  /// Define um destino ao fazer long press no mapa.
  void _definirDestinoNoMapa(LatLng ponto) {
    setState(() {
      _pontoDestino = ponto;
      _nomeDestino = 'Ponto no mapa';
      _filtroProximidadeAtivo = true;
      _buscaController.text =
          '${ponto.latitude.toStringAsFixed(5)}, ${ponto.longitude.toStringAsFixed(5)}';
    });

    _buscarVagasProximas();
  }

  /// Limpa o filtro de proximidade e volta a exibir todas as vagas.
  void _limparFiltro() {
    setState(() {
      _pontoDestino = null;
      _nomeDestino = null;
      _filtroProximidadeAtivo = false;
      _vagasProximas = null;
      _buscaController.clear();
      _resultadosBusca = [];
      _mostrandoResultados = false;
    });

    _carregarVagas();
    _centralizarMapa();
  }

  /// Encurta o nome de exibição do Nominatim para algo mais amigável.
  String _encurtarNome(String nomeCompleto) {
    final partes = nomeCompleto.split(',');
    if (partes.length >= 2) {
      return '${partes[0].trim()}, ${partes[1].trim()}';
    }
    return nomeCompleto.length > 40
        ? '${nomeCompleto.substring(0, 37)}...'
        : nomeCompleto;
  }

  /// Formata distância para exibição amigável.
  String _formatarDistancia(double km) {
    if (km < 1.0) {
      return '${(km * 1000).round()} m';
    }
    return '${km.toStringAsFixed(1)} km';
  }

  /// Calcula distância Haversine localmente (para fallback quando a API não retorna).
  double _calcularDistanciaKm(LatLng a, LatLng b) {
    const R = 6371.0; // Raio da Terra em km
    final dLat = _toRad(b.latitude - a.latitude);
    final dLon = _toRad(b.longitude - a.longitude);
    final sinDLat = math.sin(dLat / 2);
    final sinDLon = math.sin(dLon / 2);
    final h = sinDLat * sinDLat +
        math.cos(_toRad(a.latitude)) *
            math.cos(_toRad(b.latitude)) *
            sinDLon *
            sinDLon;
    return R * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h));
  }

  double _toRad(double deg) => deg * math.pi / 180;

  /// Exibe um BottomSheet com detalhes da vaga selecionada.
  void _mostrarDetalhesVaga(VagaEstacionamento vaga) {
    final bool livre = vaga.status == 0;

    // Calcula distância se o filtro está ativo
    double? distancia = vaga.distanciaKm;
    if (distancia == null && _pontoDestino != null && vaga.temCoordenadaValida) {
      distancia = _calcularDistanciaKm(
        _pontoDestino!,
        LatLng(vaga.latitude, vaga.longitude),
      );
    }

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
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 3),
                              decoration: BoxDecoration(
                                color: livre
                                    ? const Color(0xFF00C853)
                                        .withValues(alpha: 0.2)
                                    : const Color(0xFFFF1744)
                                        .withValues(alpha: 0.2),
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
                            if (distancia != null) ...[
                              const SizedBox(width: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 10, vertical: 3),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF448AFF)
                                      .withValues(alpha: 0.2),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    const Icon(
                                      Icons.near_me_rounded,
                                      color: Color(0xFF82B1FF),
                                      size: 12,
                                    ),
                                    const SizedBox(width: 4),
                                    Text(
                                      _formatarDistancia(distancia),
                                      style: const TextStyle(
                                        color: Color(0xFF82B1FF),
                                        fontWeight: FontWeight.w600,
                                        fontSize: 13,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ],
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
              if (distancia != null) ...[
                const SizedBox(height: 10),
                _detalheRow(
                  Icons.straighten_rounded,
                  'Distância do destino',
                  _formatarDistancia(distancia),
                ),
              ],
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
  // Lista de vagas a exibir (com ou sem filtro)
  // -----------------------------------------------------------------------

  /// Retorna as vagas que devem ser exibidas no mapa, dependendo do filtro.
  List<VagaEstacionamento> get _vagasExibidas {
    if (_filtroProximidadeAtivo && _vagasProximas != null) {
      return _vagasProximas!;
    }
    return _vagas;
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
          if (_mostrandoResultados) _buildResultadosBusca(),
          _buildIndicadorStatus(),
          if (_filtroProximidadeAtivo) _buildPainelFiltro(),
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
          onLongPress: (tapPosition, point) => _definirDestinoNoMapa(point),
        ),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.example.front',
          ),
          // Círculo de raio do filtro de proximidade
          if (_filtroProximidadeAtivo && _pontoDestino != null)
            CircleLayer(
              circles: [
                CircleMarker(
                  point: _pontoDestino!,
                  radius: _raioFiltroKm * 1000, // Converter km para metros
                  useRadiusInMeter: true,
                  color: const Color(0xFF448AFF).withValues(alpha: 0.08),
                  borderColor: const Color(0xFF448AFF).withValues(alpha: 0.4),
                  borderStrokeWidth: 2,
                ),
              ],
            ),
          // Camada de marcadores das vagas
          MarkerLayer(markers: _buildMarcadoresVagas()),
          // Marcador do ponto de destino
          if (_pontoDestino != null)
            MarkerLayer(
              markers: [
                Marker(
                  point: _pontoDestino!,
                  width: 48,
                  height: 48,
                  alignment: Alignment.topCenter,
                  child: const _MarcadorDestino(),
                ),
              ],
            ),
        ],
      ),
    );
  }

  /// Gera a lista de Markers para cada vaga.
  List<Marker> _buildMarcadoresVagas() {
    final vagas = _vagasExibidas;
    return List.generate(vagas.length, (i) {
      final vaga = vagas[i];
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
          controller: _buscaController,
          focusNode: _buscaFocusNode,
          onChanged: (value) {
            _debounce?.cancel();
            _debounce = Timer(const Duration(milliseconds: 500), () {
              _buscarEndereco(value);
            });
          },
          decoration: InputDecoration(
            hintText: 'Buscar destino para filtrar vagas...',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: _filtroProximidadeAtivo
                ? IconButton(
                    icon: const Icon(Icons.close, color: Color(0xFFFF1744)),
                    onPressed: _limparFiltro,
                    tooltip: 'Limpar filtro',
                  )
                : (_buscandoEndereco
                    ? const Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    : IconButton(
                        icon: const Icon(Icons.my_location_rounded),
                        onPressed: () {
                          // Placeholder: usar localização real do dispositivo
                        },
                        tooltip: 'Usar localização atual',
                      )),
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

  /// Painel de resultados da busca de endereço.
  Widget _buildResultadosBusca() {
    final topoSeguro = MediaQuery.of(context).padding.top;

    return Positioned(
      top: topoSeguro + 68,
      left: 16,
      right: 16,
      child: Material(
        elevation: 8,
        borderRadius: BorderRadius.circular(12),
        color: const Color(0xFF1E1E2C),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Dica de long-press
              Container(
                width: double.infinity,
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: const Color(0xFF448AFF).withValues(alpha: 0.1),
                  border: const Border(
                    bottom: BorderSide(color: Colors.white12),
                  ),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.touch_app_rounded,
                        color: Color(0xFF82B1FF), size: 14),
                    SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        'Ou segure no mapa para marcar o destino',
                        style: TextStyle(
                          color: Color(0xFF82B1FF),
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              ..._resultadosBusca.map((resultado) {
                return InkWell(
                  onTap: () => _selecionarDestino(resultado),
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 12),
                    decoration: const BoxDecoration(
                      border:
                          Border(bottom: BorderSide(color: Colors.white12)),
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.location_on_rounded,
                          color: Color(0xFFFF6E40),
                          size: 20,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            resultado.nomeExibicao,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 13,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const Icon(
                          Icons.arrow_forward_ios_rounded,
                          color: Colors.white24,
                          size: 14,
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ],
          ),
        ),
      ),
    );
  }

  /// Painel do filtro de proximidade com slider de raio.
  Widget _buildPainelFiltro() {
    final bottomSeguro = MediaQuery.of(context).padding.bottom;

    final vagasExibidas = _vagasExibidas;
    final livres = vagasExibidas.where((v) => v.status == 0).length;
    final total = vagasExibidas.length;

    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(16, 16, 16, bottomSeguro + 16),
        decoration: BoxDecoration(
          color: const Color(0xFF1E1E2C).withValues(alpha: 0.96),
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.4),
              blurRadius: 20,
              offset: const Offset(0, -4),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header com nome do destino e botão de fechar
            Row(
              children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: const Color(0xFFFF6E40).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(
                    Icons.flag_rounded,
                    color: Color(0xFFFF6E40),
                    size: 20,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Filtrando por proximidade',
                        style: TextStyle(
                          color: Colors.white54,
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      Text(
                        _nomeDestino ?? 'Destino',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                // Contagem de vagas encontradas
                if (!_buscandoProximas)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFF00C853).withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '$livres/$total vagas',
                      style: const TextStyle(
                        color: Color(0xFF00E676),
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                if (_buscandoProximas)
                  const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white54,
                    ),
                  ),
                const SizedBox(width: 8),
                GestureDetector(
                  onTap: _limparFiltro,
                  child: Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: const Color(0xFFFF1744).withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(
                      Icons.close_rounded,
                      color: Color(0xFFFF5252),
                      size: 18,
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 14),

            // Slider de raio
            Row(
              children: [
                const Icon(
                  Icons.radar_rounded,
                  color: Color(0xFF448AFF),
                  size: 18,
                ),
                const SizedBox(width: 8),
                Text(
                  'Raio: ${_formatarDistancia(_raioFiltroKm)}',
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
            SliderTheme(
              data: SliderThemeData(
                activeTrackColor: const Color(0xFF448AFF),
                inactiveTrackColor:
                    const Color(0xFF448AFF).withValues(alpha: 0.2),
                thumbColor: const Color(0xFF448AFF),
                overlayColor: const Color(0xFF448AFF).withValues(alpha: 0.15),
                trackHeight: 4,
                thumbShape:
                    const RoundSliderThumbShape(enabledThumbRadius: 8),
              ),
              child: Slider(
                value: _raioFiltroKm,
                min: 0.1,
                max: 5.0,
                divisions: 49,
                onChanged: (value) {
                  setState(() => _raioFiltroKm = value);
                },
                onChangeEnd: (_) => _buscarVagasProximas(),
              ),
            ),
          ],
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

    // Não mostra este indicador quando o painel de filtro está ativo
    if (_filtroProximidadeAtivo) return const SizedBox.shrink();

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
      bottom: _filtroProximidadeAtivo ? 180 : 24,
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
      bottom: _filtroProximidadeAtivo ? 246 : 90,
      child: FloatingActionButton.small(
        heroTag: 'atualizar',
        onPressed:
            _filtroProximidadeAtivo ? _buscarVagasProximas : _carregarVagas,
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
      bottom: _filtroProximidadeAtivo ? 180 : 24,
      child: FloatingActionButton(
        heroTag: 'centralizar',
        onPressed: _filtroProximidadeAtivo && _pontoDestino != null
            ? () => _mapController.move(_pontoDestino!, 16.0)
            : _centralizarMapa,
        tooltip: _filtroProximidadeAtivo
            ? 'Centralizar no destino'
            : 'Centralizar em Concórdia',
        child: Icon(_filtroProximidadeAtivo
            ? Icons.flag_rounded
            : Icons.my_location),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Widget do marcador de destino
// ---------------------------------------------------------------------------

/// Marcador visual do ponto de destino no mapa.
class _MarcadorDestino extends StatelessWidget {
  const _MarcadorDestino();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: const Color(0xFFFF6E40),
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white, width: 3),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFFFF6E40).withValues(alpha: 0.5),
                blurRadius: 12,
                spreadRadius: 2,
              ),
            ],
          ),
          child: const Icon(
            Icons.flag_rounded,
            color: Colors.white,
            size: 18,
          ),
        ),
        // Triângulo apontando para baixo (seta do pin)
        CustomPaint(
          size: const Size(12, 8),
          painter: _TrianglePainter(color: const Color(0xFFFF6E40)),
        ),
      ],
    );
  }
}

/// Painter para desenhar o triângulo do pin de destino.
class _TrianglePainter extends CustomPainter {
  final Color color;
  const _TrianglePainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color;
    final path = Path()
      ..moveTo(0, 0)
      ..lineTo(size.width / 2, size.height)
      ..lineTo(size.width, 0)
      ..close();
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

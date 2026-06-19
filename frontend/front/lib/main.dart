import 'package:flutter/material.dart';
import 'package:front/pages/dashboard_page.dart';
import 'mapa_page.dart';
import 'pagina_login.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Estacionei',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF000000)),
        useMaterial3: true,
      ),
      home: const LoginPage(),
      routes: {
        '/mapa': (context) => const MapaPage(),
        '/dashboard': (context) => const DashboardPage(),
      },
    );
  }
}


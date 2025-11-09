<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:output method="html" indent="yes"/>

  <!-- ========= Helpers: parsing and formatting ========= -->

  <!-- Pad 2 digits -->
  <xsl:template name="pad2">
    <xsl:param name="n"/>
    <xsl:choose>
      <xsl:when test="$n &lt; 10">0<xsl:value-of select="$n"/></xsl:when>
      <xsl:otherwise><xsl:value-of select="$n"/></xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Month abbrev -> number (1..12) -->
  <xsl:template name="month-num">
    <xsl:param name="mon"/>
    <xsl:choose>
      <xsl:when test="$mon='Jan'">1</xsl:when>
      <xsl:when test="$mon='Feb'">2</xsl:when>
      <xsl:when test="$mon='Mar'">3</xsl:when>
      <xsl:when test="$mon='Apr'">4</xsl:when>
      <xsl:when test="$mon='May'">5</xsl:when>
      <xsl:when test="$mon='Jun'">6</xsl:when>
      <xsl:when test="$mon='Jul'">7</xsl:when>
      <xsl:when test="$mon='Aug'">8</xsl:when>
      <xsl:when test="$mon='Sep'">9</xsl:when>
      <xsl:when test="$mon='Oct'">10</xsl:when>
      <xsl:when test="$mon='Nov'">11</xsl:when>
      <xsl:when test="$mon='Dec'">12</xsl:when>
      <xsl:otherwise>1</xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Month number -> abbrev -->
  <xsl:template name="month-abbr">
    <xsl:param name="m"/>
    <xsl:choose>
      <xsl:when test="$m=1">Jan</xsl:when>
      <xsl:when test="$m=2">Feb</xsl:when>
      <xsl:when test="$m=3">Mar</xsl:when>
      <xsl:when test="$m=4">Apr</xsl:when>
      <xsl:when test="$m=5">May</xsl:when>
      <xsl:when test="$m=6">Jun</xsl:when>
      <xsl:when test="$m=7">Jul</xsl:when>
      <xsl:when test="$m=8">Aug</xsl:when>
      <xsl:when test="$m=9">Sep</xsl:when>
      <xsl:when test="$m=10">Oct</xsl:when>
      <xsl:when test="$m=11">Nov</xsl:when>
      <xsl:when test="$m=12">Dec</xsl:when>
      <xsl:otherwise>Jan</xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Weekday abbrev -> index (Sun=0..Sat=6) -->
  <xsl:template name="wday-index">
    <xsl:param name="w"/>
    <xsl:choose>
      <xsl:when test="$w='Sun'">0</xsl:when>
      <xsl:when test="$w='Mon'">1</xsl:when>
      <xsl:when test="$w='Tue'">2</xsl:when>
      <xsl:when test="$w='Wed'">3</xsl:when>
      <xsl:when test="$w='Thu'">4</xsl:when>
      <xsl:when test="$w='Fri'">5</xsl:when>
      <xsl:when test="$w='Sat'">6</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Weekday index -> abbrev -->
  <xsl:template name="wday-abbr">
    <xsl:param name="i"/>
    <xsl:variable name="n" select="($i mod 7 + 7) mod 7"/>
    <xsl:choose>
      <xsl:when test="$n=0">Sun</xsl:when>
      <xsl:when test="$n=1">Mon</xsl:when>
      <xsl:when test="$n=2">Tue</xsl:when>
      <xsl:when test="$n=3">Wed</xsl:when>
      <xsl:when test="$n=4">Thu</xsl:when>
      <xsl:when test="$n=5">Fri</xsl:when>
      <xsl:when test="$n=6">Sat</xsl:when>
      <xsl:otherwise>Sun</xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Leap year? returns 1 or 0 -->
  <xsl:template name="is-leap">
    <xsl:param name="y"/>
    <!-- leap if (y % 400 == 0) or (y % 4 == 0 and y % 100 != 0) -->
    <xsl:variable name="mod4" select="$y - 4 * floor($y div 4)"/>
    <xsl:variable name="mod100" select="$y - 100 * floor($y div 100)"/>
    <xsl:variable name="mod400" select="$y - 400 * floor($y div 400)"/>
    <xsl:choose>
      <xsl:when test="$mod400 = 0">1</xsl:when>
      <xsl:when test="$mod4 = 0 and not($mod100 = 0)">1</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- Days in month -->
  <xsl:template name="days-in-month">
    <xsl:param name="m"/>
    <xsl:param name="y"/>
    <xsl:choose>
      <xsl:when test="$m=1 or $m=3 or $m=5 or $m=7 or $m=8 or $m=10 or $m=12">31</xsl:when>
      <xsl:when test="$m=4 or $m=6 or $m=9 or $m=11">30</xsl:when>
      <xsl:otherwise>
        <!-- February -->
        <xsl:variable name="leap">
          <xsl:call-template name="is-leap"><xsl:with-param name="y" select="$y"/></xsl:call-template>
        </xsl:variable>
        <xsl:choose>
          <xsl:when test="$leap = 1">29</xsl:when>
          <xsl:otherwise>28</xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <!-- ====== GMT → EST exact (handles date/month/year + weekday roll-back) ====== -->
  <!-- Expects RFC-822 string: "Wed, 05 Nov 2025 03:12:45 GMT" -->
  <xsl:template name="to-est-exact">
    <xsl:param name="gmt"/>

    <!-- Parse components via fixed positions -->
    <xsl:variable name="wday" select="substring($gmt, 1, 3)"/>
    <xsl:variable name="day"  select="number(substring($gmt, 6, 2))"/>
    <xsl:variable name="mon"  select="substring($gmt, 9, 3)"/>
    <xsl:variable name="year" select="number(substring($gmt, 13, 4))"/>
    <xsl:variable name="hh"   select="number(substring($gmt, 18, 2))"/>
    <xsl:variable name="mm"   select="substring($gmt, 21, 2)"/>
    <xsl:variable name="ss"   select="substring($gmt, 24, 2)"/>

    <!-- Month number -->
    <xsl:variable name="mnum">
      <xsl:call-template name="month-num"><xsl:with-param name="mon" select="$mon"/></xsl:call-template>
    </xsl:variable>

    <!-- Apply fixed EST offset: -5 hours -->
    <xsl:variable name="hh_adj" select="$hh - 5"/>

    <!-- Did we cross to previous day? -->
    <xsl:variable name="rollPrevDay" select="($hh_adj &lt; 0)"/>

    <!-- New hour in 0..23 -->
    <xsl:variable name="new_hh">
      <xsl:choose>
        <xsl:when test="$rollPrevDay">
          <xsl:value-of select="$hh_adj + 24"/>
        </xsl:when>
        <xsl:otherwise><xsl:value-of select="$hh_adj"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>

    <!-- Adjust date/month/year if rolled -->
    <xsl:variable name="tmp_day">
      <xsl:choose>
        <xsl:when test="$rollPrevDay"><xsl:value-of select="$day - 1"/></xsl:when>
        <xsl:otherwise><xsl:value-of select="$day"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>

    <!-- If day becomes 0, move to previous month -->
    <xsl:variable name="prev_mnum">
      <xsl:choose>
        <xsl:when test="$tmp_day &lt;= 0">
          <xsl:choose>
            <xsl:when test="$mnum = 1">12</xsl:when>
            <xsl:otherwise><xsl:value-of select="$mnum - 1"/></xsl:otherwise>
          </xsl:choose>
        </xsl:when>
        <xsl:otherwise><xsl:value-of select="$mnum"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>

    <xsl:variable name="prev_year">
      <xsl:choose>
        <xsl:when test="$tmp_day &lt;= 0 and $mnum = 1"><xsl:value-of select="$year - 1"/></xsl:when>
        <xsl:otherwise><xsl:value-of select="$year"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>

    <!-- Days in the (possibly previous) month -->
    <xsl:variable name="days_in_prev_month">
      <xsl:call-template name="days-in-month">
        <xsl:with-param name="m" select="$prev_mnum"/>
        <xsl:with-param name="y" select="$prev_year"/>
      </xsl:call-template>
    </xsl:variable>

    <!-- Final day -->
    <xsl:variable name="new_day">
      <xsl:choose>
        <xsl:when test="$tmp_day &lt;= 0"><xsl:value-of select="$days_in_prev_month"/></xsl:when>
        <xsl:otherwise><xsl:value-of select="$tmp_day"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>

    <!-- Final month num -->
    <xsl:variable name="new_mnum">
      <xsl:choose>
        <xsl:when test="$tmp_day &lt;= 0"><xsl:value-of select="$prev_mnum"/></xsl:when>
        <xsl:otherwise><xsl:value-of select="$mnum"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>

    <!-- Final year -->
    <xsl:variable name="new_year" select="$prev_year"/>

    <!-- Weekday shift (roll back 1 if we crossed to previous day) -->
    <xsl:variable name="widx">
      <xsl:call-template name="wday-index"><xsl:with-param name="w" select="$wday"/></xsl:call-template>
    </xsl:variable>
    <xsl:variable name="new_widx">
      <xsl:choose>
        <xsl:when test="$rollPrevDay"><xsl:value-of select="$widx - 1"/></xsl:when>
        <xsl:otherwise><xsl:value-of select="$widx"/></xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:variable name="new_wday">
      <xsl:call-template name="wday-abbr"><xsl:with-param name="i" select="$new_widx"/></xsl:call-template>
    </xsl:variable>

    <!-- Month abbrev -->
    <xsl:variable name="new_mon">
      <xsl:call-template name="month-abbr"><xsl:with-param name="m" select="$new_mnum"/></xsl:call-template>
    </xsl:variable>

    <!-- Zero-pad hour and day -->
    <xsl:variable name="hh2">
      <xsl:call-template name="pad2"><xsl:with-param name="n" select="$new_hh"/></xsl:call-template>
    </xsl:variable>
    <xsl:variable name="day2">
      <xsl:call-template name="pad2"><xsl:with-param name="n" select="$new_day"/></xsl:call-template>
    </xsl:variable>

    <!-- Build final RFC-822 style string -->
    <xsl:value-of select="concat($new_wday, ', ', $day2, ' ', $new_mon, ' ', $new_year, ' ', $hh2, ':', $mm, ':', $ss, ' EST')"/>
  </xsl:template>
  <!-- ========= End helpers ========= -->

  <xsl:template match="/">
    <html>
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title><xsl:value-of select="rss/channel/title"/></title>
        <style>
          :root{
            --dcl-navy:#16578A;
            --dcl-gold:#C9A227;
            --ink:#1b1b1b;
            --muted:#6b6f76;
            --bg:#16578A;
            --card:#ffffff;
            --line:#e9edf2;
            --pill:#eef4fb;
          }
          *{box-sizing:border-box}
          body{
            margin:0;
            background:var(--bg);
            color:var(--ink);
            font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,Helvetica,sans-serif;
          }
          .bar{background:#ffffff;color:var(--dcl-navy);padding:14px 18px;border-bottom:4px solid var(--dcl-gold);}
          .brand{display:flex;flex-direction:column;align-items:center;text-align:center;gap:6px;max-width:1100px;margin:0 auto;}
          .logo-img{width:325px;height:auto;display:block;margin:0 auto;}
          .brand h1{margin:0;font-size:18px;line-height:1.2;font-weight:700;color:var(--dcl-navy);}
          .wrap{max-width:1100px;margin:18px auto;padding:0 16px}
          .card{background:var(--card);border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,.10);border:1px solid var(--line);}
          .meta{padding:14px 16px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px;}
          .meta a{color:var(--dcl-navy);text-decoration:underline}
          .chip{background:var(--pill);color:var(--dcl-navy);border:1px solid #d7e5f6;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:600;}
          table{width:100%;border-collapse:collapse;font-size:14px;background:#fff}
          thead th{position:sticky;top:0;background:#fbfdff;z-index:1;text-align:left;padding:12px 14px;border-bottom:2px solid var(--line);color:#133c5e;font-weight:700;}
          tbody td{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top;}
          tbody tr:hover{background:#fbfdff}
          .title a{color:var(--dcl-navy);text-decoration:none;font-weight:700}
          .title a:hover{text-decoration:underline}
          .guid{font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--muted);font-size:12px}
          .desc{white-space:pre-wrap}
          .badge{display:inline-block;padding:3px 8px;border-radius:6px;font-weight:700;font-size:12px;border:1px solid transparent;margin-right:8px;}
          .arr{background:#e8f6ee;color:#11643a;border-color:#cfead9}
          .dep{background:#fff0f0;color:#8a1620;border-color:#ffd9de}
          @media (max-width:760px){
            thead{display:none}
            tbody tr{display:block;border-bottom:8px solid #f0f4f8}
            tbody td{display:block;border:0;padding:8px 14px}
            tbody td::before{content:attr(data-label) ' ';font-weight:600;color:var(--muted);display:block;margin-bottom:2px}
            .brand{gap:8px}
          }
        </style>
      </head>
      <body>
        <div class="bar">
          <div class="brand">
            <img src="DCLDailySummary.png" alt="DCL Logo" class="logo-img"/>
            <h1><xsl:value-of select="rss/channel/title"/></h1>
          </div>
        </div>
        <div class="wrap">
          <div class="card">
            <div class="meta">
              <span class="chip">DCL • Airport &amp; Resort Reporting</span>
              <span><strong>Feed link:</strong> <a href="{rss/channel/link}"><xsl:value-of select="rss/channel/link"/></a></span>
              <!-- Last Build in true EST with date roll-over -->
              <span>
                <strong>Last Build:</strong>
                <xsl:call-template name="to-est-exact">
                  <xsl:with-param name="gmt" select="rss/channel/lastBuildDate"/>
                </xsl:call-template>
              </span>
            </div>
            <table role="table" aria-label="Items">
              <thead><tr><th>Title</th><th>Published</th><th>Description</th></tr></thead>
              <tbody>
                <xsl:for-each select="rss/channel/item">
                  <tr>
                    <td class="title" data-label="Title">
                      <span class="badge">
                        <xsl:attribute name="class">
                          <xsl:text>badge </xsl:text>
                          <xsl:choose>
                            <xsl:when test="contains(title,'Arrived')">arr</xsl:when>
                            <xsl:otherwise>dep</xsl:otherwise>
                          </xsl:choose>
                        </xsl:attribute>
                        <xsl:choose>
                          <xsl:when test="contains(title,'Arrived')">ARRIVED</xsl:when>
                          <xsl:otherwise>DEPARTED</xsl:otherwise>
                        </xsl:choose>
                      </span>
                      <a href="{link}"><xsl:value-of select="title"/></a><br/>
                      <span class="guid"><xsl:value-of select="guid"/></span>
                    </td>

                    <!-- Published in true EST with date roll-over -->
                    <td data-label="Published">
                      <xsl:call-template name="to-est-exact">
                        <xsl:with-param name="gmt" select="pubDate"/>
                      </xsl:call-template>
                    </td>

                    <td class="desc" data-label="Description">
                      <xsl:value-of select="description" disable-output-escaping="yes"/>
                    </td>
                  </tr>
                </xsl:for-each>
              </tbody>
            </table>
          </div>
        </div>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
